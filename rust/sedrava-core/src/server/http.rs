//! Limited HTTP/1.1 framing for the local native preview.
//! Each accepted TCP connection carries exactly one request; always close.
use super::{reply_stateful, Server, Session, MAX_REQUEST_BODY};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};

const HEADER_MAX: usize = 8192;
const MAX_HEADER_COUNT: usize = 32;

#[derive(Debug)]
pub struct Response {
    pub status: u16,
    pub body: Value,
    pub allow: Option<String>,
}

impl Response {
    pub fn json(status: u16, body: Value) -> Self {
        Self {
            status,
            body,
            allow: None,
        }
    }
    pub fn error(status: u16, code: &str) -> Self {
        Self::json(status, json!({"error":{"code":code}}))
    }
    pub fn with_allow(mut self, methods: String) -> Self {
        self.allow = Some(methods);
        self
    }
}

struct Request {
    method: String,
    path: String,
    content_type: Option<String>,
    body: Vec<u8>,
}

fn separator(raw: &[u8]) -> Option<usize> {
    raw.windows(4).position(|v| v == b"\r\n\r\n")
}

fn read_deadline(
    stream: &mut TcpStream,
    buf: &mut [u8],
    deadline: Instant,
) -> std::io::Result<usize> {
    let remaining = deadline.saturating_duration_since(Instant::now());
    if remaining.is_zero() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::TimedOut,
            "HTTP request deadline exceeded",
        ));
    }
    stream.set_read_timeout(Some(remaining))?;
    stream.read(buf)
}

fn parse_request(stream: &mut TcpStream) -> std::result::Result<Request, Response> {
    // Absolute cap, not a timeout reset per byte (slowloris guard).
    let deadline = Instant::now() + Duration::from_millis(1500);
    let mut raw = Vec::new();
    let mut buffer = [0u8; 1024];
    let boundary = loop {
        if let Some(start) = separator(&raw) {
            if start + 4 > HEADER_MAX {
                return Err(Response::error(431, "HEADERS_TOO_LARGE"));
            }
            break start + 4;
        }
        if raw.len() >= HEADER_MAX {
            return Err(Response::error(431, "HEADERS_TOO_LARGE"));
        }
        let count = read_deadline(stream, &mut buffer, deadline)
            .map_err(|_| Response::error(400, "INCOMPLETE_HEADERS"))?;
        if count == 0 {
            return Err(Response::error(400, "INCOMPLETE_HEADERS"));
        }
        raw.extend_from_slice(&buffer[..count]);
    };
    let header = std::str::from_utf8(&raw[..boundary])
        .map_err(|_| Response::error(400, "INVALID_HEADERS"))?;
    let mut lines = header[..header.len() - 4].split("\r\n");
    let line = lines
        .next()
        .ok_or_else(|| Response::error(400, "INVALID_REQUEST_LINE"))?;
    let words: Vec<_> = line.split(' ').collect();
    if words.len() != 3 || words[2] != "HTTP/1.1" {
        return Err(Response::error(400, "INVALID_REQUEST_LINE"));
    }
    let method = words[0];
    let path = words[1];
    if !matches!(
        method,
        "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS"
    ) || !super::pathname(path)
    {
        return Err(Response::error(400, "INVALID_REQUEST_TARGET"));
    }
    let mut headers = BTreeMap::new();
    for item in lines {
        if headers.len() >= MAX_HEADER_COUNT {
            return Err(Response::error(431, "TOO_MANY_HEADERS"));
        }
        let (key, value) = item
            .split_once(':')
            .ok_or_else(|| Response::error(400, "INVALID_HEADER"))?;
        if key.is_empty() || !key.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-') {
            return Err(Response::error(400, "INVALID_HEADER"));
        }
        let name = key.to_ascii_lowercase();
        let value = value.trim();
        if value.bytes().any(|c| c.is_ascii_control()) || headers.contains_key(&name) {
            return Err(Response::error(400, "INVALID_OR_DUPLICATE_HEADER"));
        }
        headers.insert(name, value);
    }
    let Some(host) = headers.get("host") else {
        return Err(Response::error(400, "HOST_REQUIRED"));
    };
    if host.is_empty() || host.len() > 255 {
        return Err(Response::error(400, "INVALID_HOST"));
    }
    // Localhost-only Host enforcement blocks ordinary DNS-rebinding origin
    // tricks. The port, when supplied, must match the actual bound port.
    let (hostname, port) = match host.rsplit_once(':') {
        Some((hostname, port)) => (hostname, Some(port)),
        None => (host.as_ref(), None),
    };
    if !matches!(hostname, "localhost" | "127.0.0.1")
        || port.is_some_and(|value| {
            value.parse::<u16>().ok() != stream.local_addr().ok().map(|addr| addr.port())
        })
    {
        return Err(Response::error(400, "INVALID_HOST"));
    }
    if headers.contains_key("transfer-encoding") {
        return Err(Response::error(400, "TRANSFER_ENCODING_UNSUPPORTED"));
    }
    let length = if let Some(value) = headers.get("content-length") {
        if value.is_empty() || !value.bytes().all(|c| c.is_ascii_digit()) {
            return Err(Response::error(400, "INVALID_CONTENT_LENGTH"));
        }
        value
            .parse::<usize>()
            .map_err(|_| Response::error(413, "BODY_TOO_LARGE"))?
    } else {
        0
    };
    if length > MAX_REQUEST_BODY {
        return Err(Response::error(413, "BODY_TOO_LARGE"));
    }
    let mut body = raw[boundary..].to_vec();
    if body.len() > length {
        return Err(Response::error(400, "UNEXPECTED_TRAILING_DATA"));
    }
    while body.len() < length {
        let remaining = length - body.len();
        let limit = remaining.min(buffer.len());
        let count = read_deadline(stream, &mut buffer[..limit], deadline)
            .map_err(|_| Response::error(400, "INCOMPLETE_BODY"))?;
        if count == 0 {
            return Err(Response::error(400, "INCOMPLETE_BODY"));
        }
        body.extend_from_slice(&buffer[..count]);
    }
    Ok(Request {
        method: method.into(),
        path: path.into(),
        content_type: headers.get("content-type").map(|s| (*s).to_string()),
        body,
    })
}

fn reason(status: u16) -> &'static str {
    match status {
        200 => "OK",
        201 => "Created",
        202 => "Accepted",
        400 => "Bad Request",
        404 => "Not Found",
        405 => "Method Not Allowed",
        413 => "Content Too Large",
        415 => "Unsupported Media Type",
        422 => "Unprocessable Content",
        503 => "Service Unavailable",
        431 => "Request Header Fields Too Large",
        _ => "Internal Server Error",
    }
}

fn write_response(stream: &mut TcpStream, response: Response) -> std::io::Result<()> {
    let (status, bytes) = match serde_json::to_vec(&response.body) {
        Ok(bytes) if bytes.len() <= 65_536 => (response.status, bytes),
        _ => (500, br#"{"error":{"code":"RESPONSE_TOO_LARGE"}}"#.to_vec()),
    };
    write!(stream,
        "HTTP/1.1 {} {}\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n",
        status,reason(status),bytes.len())?;
    if let Some(allowed) = response.allow.as_deref() {
        write!(stream, "Allow: {allowed}\r\n")?;
    }
    stream.write_all(b"\r\n")?;
    stream.write_all(&bytes)?;
    stream.flush()
}

pub(super) fn process(server: &Server, session: &mut Session, stream: &mut TcpStream) {
    let response = match parse_request(stream) {
        Ok(request) => reply_stateful(
            server,
            session,
            &request.method,
            &request.path,
            &request.body,
            request.content_type.as_deref(),
        ),
        Err(error) => error,
    };
    // The peer may disappear. Never crash the process for a single socket.
    let _ = write_response(stream, response);
    // Large malformed headers may leave unread TCP bytes in the receive
    // buffer. Linux can reset the connection on close and discard our JSON
    // error response. Half-close writing and best-effort drain a strictly
    // limited amount (up to 24 KiB / 80 ms) without processing pipelining.
    let _ = stream.shutdown(std::net::Shutdown::Write);
    let _ = stream.set_read_timeout(Some(std::time::Duration::from_millis(80)));
    let mut scratch = [0u8; 2048];
    for _ in 0..12 {
        match stream.read(&mut scratch) {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{TcpListener, TcpStream};
    use std::thread;
    fn make(raw: &[u8]) -> Response {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        let bytes = raw.to_vec();
        let thread = thread::spawn(move || {
            let mut stream = TcpStream::connect(addr).unwrap();
            stream.write_all(&bytes).unwrap();
            stream.shutdown(std::net::Shutdown::Write).unwrap();
        });
        let (mut stream, _) = listener.accept().unwrap();
        stream
            .set_read_timeout(Some(std::time::Duration::from_millis(800)))
            .unwrap();
        let result = parse_request(&mut stream);
        thread.join().unwrap();
        match result {
            Ok(_) => Response::json(200, json!({"ok":true})),
            Err(e) => e,
        }
    }
    #[test]
    fn rejects_ambiguous_http_framing() {
        for text in [
            "POST /health HTTP/1.1\r\nHost: x\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx",
            "POST /health HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n",
            "POST /health HTTP/1.1\r\nHost: x\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\nx",
            "POST /health HTTP/1.1\r\nHost: x\r\nContent-Length: banana\r\n\r\n",
            "POST /health HTTP/1.1\r\nHost: x\r\nContent-Length: 999999\r\n\r\n",
            "POST /health HTTP/1.1\r\nHost: x\r\nBad Header: hello\r\n\r\n",
            "POST /health HTTP/1.1\r\nHost: x\r\nX-A: 1\r\nX-A: 2\r\n\r\n",
            "POST /health HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
            "GET http://evil/x HTTP/1.1\r\nHost: x\r\n\r\n",
            "GET /hi%2fthere HTTP/1.1\r\nHost: x\r\n\r\n",
            "GET /health HTTP/1.0\r\nHost: x\r\n\r\n",
        ] {
            assert_ne!(make(text.as_bytes()).status,200,"{text}");
        }
    }
    #[test]
    fn reads_complete_small_body() {
        assert_eq!(make(
            b"POST /health HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}"
        ).status,200);
    }
}
