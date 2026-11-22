use crate::model::{fail, Error, Result};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    io::Read,
    path::{Path, PathBuf},
    sync::LazyLock,
};

const MAX_ASSET: usize = 2 * 1024 * 1024;
const MAX_TOTAL: usize = 16 * 1024 * 1024;

pub(super) fn read_local(
    root: &Path,
    base: &Path,
    value: &str,
    types: &[&str],
    limit: usize,
) -> Result<(PathBuf, Vec<u8>)> {
    if value
        .split('/')
        .any(|part| part.is_empty() || matches!(part, "." | ".."))
        || value.contains(['\\', ':', '%', '?', '#'])
        || value.chars().any(char::is_control)
    {
        return fail("Expected a local path within the source directory");
    }
    let path = base.join(value);
    let relative = path
        .strip_prefix(root)
        .map_err(|_| Error("Expected a local path within the source directory".into()))?;
    if !types.contains(&extension(&path).as_str()) {
        return fail("Unsupported Site asset or module");
    }
    let read_error = |error| Error(format!("Cannot read {value}: {error}"));
    let input = open_local(root, relative).map_err(read_error)?;
    if !input.metadata().map_err(read_error)?.is_file() {
        return fail("Site assets and modules must be regular files");
    }
    let mut data = Vec::new();
    input
        .take(limit as u64 + 1)
        .read_to_end(&mut data)
        .map_err(read_error)?;
    if data.len() > limit {
        return fail("Site asset or module exceeds size limit");
    }
    Ok((path, data))
}

#[cfg(unix)]
fn open_local(root: &Path, relative: &Path) -> std::io::Result<fs::File> {
    use rustix::fs::{open, openat, Mode, OFlags};
    let flags = OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK;
    let mut dir = open(root, flags | OFlags::DIRECTORY, Mode::empty())?;
    let mut parts = relative.components().peekable();
    while let Some(std::path::Component::Normal(part)) = parts.next() {
        if parts.peek().is_none() {
            return Ok(openat(&dir, part, flags, Mode::empty())?.into());
        }
        dir = openat(&dir, part, flags | OFlags::DIRECTORY, Mode::empty())?;
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::InvalidInput,
        "Invalid local path",
    ))
}

#[cfg(not(unix))]
fn open_local(root: &Path, relative: &Path) -> std::io::Result<fs::File> {
    let mut path = root.to_path_buf();
    for part in relative.components() {
        path.push(part);
        if fs::symlink_metadata(&path)?.is_symlink() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "Symlink Site asset or module",
            ));
        }
    }
    let resolved = path.canonicalize()?;
    if !resolved.starts_with(root) || !resolved.is_file() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "Expected local regular file",
        ));
    }
    fs::File::open(resolved)
}

fn extension(path: &Path) -> String {
    path.extension()
        .and_then(|v| v.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
}

fn utf8(data: &[u8]) -> Result<&str> {
    std::str::from_utf8(data).map_err(|_| Error("Site text assets must use UTF-8".into()))
}

fn validate_svg(data: &[u8]) -> Result<()> {
    const SVG: &str = "http://www.w3.org/2000/svg";
    const TAGS: &[&str] = &[
        "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text",
        "tspan", "title", "desc",
    ];
    const ATTRS: &[&str] = &[
        "viewBox",
        "width",
        "height",
        "x",
        "y",
        "x1",
        "x2",
        "y1",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "d",
        "points",
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
        "transform",
        "font-family",
        "font-size",
        "font-weight",
        "text-anchor",
        "dominant-baseline",
        "id",
    ];
    static RESOURCE: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"(?i)url\s*\(|https?:|data:|javascript:|@import|/\*").unwrap()
    });
    let text = utf8(data)?.trim_start_matches('\u{feff}');
    let document =
        roxmltree::Document::parse(text).map_err(|e| Error(format!("Invalid SVG XML: {e}")))?;
    let root = document.root_element().tag_name();
    if root.namespace() != Some(SVG) || root.name() != "svg" {
        return fail("Expected SVG namespace and root");
    }
    for node in document.descendants() {
        if node.is_pi() {
            return fail("SVG processing instructions are forbidden");
        }
        if node.is_element()
            && (node.tag_name().namespace() != Some(SVG)
                || !TAGS.contains(&node.tag_name().name())
                || node.attributes().any(|attr| {
                    attr.namespace().is_some()
                        || !ATTRS.contains(&attr.name())
                        || attr.value().contains('\\')
                        || RESOURCE.is_match(attr.value())
                }))
        {
            return fail("Unsafe SVG element, attribute or resource reference");
        }
    }
    Ok(())
}

pub(super) struct Assets<'a> {
    root: Option<&'a Path>,
    pub files: BTreeMap<String, Vec<u8>>,
    cache: BTreeMap<(PathBuf, String), String>,
    total: usize,
}

impl<'a> Assets<'a> {
    pub fn new(root: Option<&'a Path>) -> Self {
        Self {
            root,
            files: BTreeMap::new(),
            cache: BTreeMap::new(),
            total: 0,
        }
    }

    fn root(&self) -> Result<&'a Path> {
        self.root
            .ok_or_else(|| Error("Site assets require a source directory".into()))
    }

    fn insert(&mut self, data: Vec<u8>, suffix: &str, prefix: &str) -> Result<String> {
        let name = format!("assets/{prefix}{:x}.{suffix}", Sha256::digest(&data));
        if !self.files.contains_key(&name) {
            self.total += data.len();
            if self.total > MAX_TOTAL {
                return fail("Combined Site assets exceed 16 MiB");
            }
            self.files.insert(name.clone(), data);
        }
        Ok(name)
    }

    pub fn image(&mut self, value: &str) -> Result<String> {
        self.resource(value, self.root()?, false)
    }

    fn resource(&mut self, value: &str, base: &Path, fonts: bool) -> Result<String> {
        const IMAGES: &[&str] = &["svg", "png", "jpg", "jpeg", "webp"];
        const RESOURCES: &[&str] = &["svg", "png", "jpg", "jpeg", "webp", "woff", "woff2"];
        let key = (base.to_path_buf(), value.to_owned());
        let types = if fonts { RESOURCES } else { IMAGES };
        if let Some(name) = self.cache.get(&key) {
            if !types.contains(&extension(Path::new(name)).as_str()) {
                return fail("Unsupported Site asset type");
            }
            return Ok(name.clone());
        }
        let (path, data) = read_local(self.root()?, base, value, types, MAX_ASSET)?;
        let suffix = extension(&path);
        let valid = match suffix.as_str() {
            "svg" => {
                validate_svg(&data)?;
                true
            }
            "png" => data.starts_with(b"\x89PNG\r\n\x1a\n"),
            "jpg" | "jpeg" => data.starts_with(b"\xff\xd8\xff"),
            "webp" => data.starts_with(b"RIFF") && data.get(8..12) == Some(b"WEBP"),
            "woff" => data.starts_with(b"wOFF"),
            "woff2" => data.starts_with(b"wOF2"),
            _ => false,
        };
        if !valid {
            return fail("Invalid Site asset signature");
        }
        let name = self.insert(data, &suffix, "")?;
        self.cache.insert(key, name.clone());
        Ok(name)
    }

    pub fn license(&mut self, value: &str) -> Result<String> {
        let root = self.root()?;
        let (_, data) = read_local(root, root, value, &["txt"], 65536)?;
        utf8(&data)?;
        self.insert(data, "txt", "license-")
    }

    pub fn stylesheet(&mut self, value: &str) -> Result<String> {
        static COMMENT: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)/\*.*?\*/").unwrap());
        static UNSAFE: LazyLock<Regex> = LazyLock::new(|| {
            Regex::new(
                r"(?i)@import|expression\s*\(|-moz-binding|(?:-webkit-)?image-set\s*\(|image\s*\(|src\s*\(",
            )
            .unwrap()
        });
        static URL_START: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?i)url\s*\(").unwrap());
        static CSS_URL: LazyLock<Regex> = LazyLock::new(|| {
            Regex::new(r#"(?i)url\(\s*(?:"([^"\r\n]+)"|'([^'\r\n]+)'|([^)"']+))\s*\)"#).unwrap()
        });
        let root = self.root()?;
        let (path, data) = read_local(root, root, value, &["css"], 262144)?;
        let css = utf8(&data)?;
        let clean = COMMENT.replace_all(css, "");
        if css.contains(['\\', '\0'])
            || clean.contains("/*")
            || UNSAFE.is_match(&clean)
            || URL_START.find_iter(&clean).count() != CSS_URL.find_iter(css).count()
        {
            return fail("Unsafe or unsupported Site stylesheet syntax");
        }
        let mut rewritten = String::new();
        let mut offset = 0;
        for capture in CSS_URL.captures_iter(css) {
            let matched = capture.get(0).unwrap();
            rewritten.push_str(&css[offset..matched.start()]);
            let target = (1..=3)
                .find_map(|i| capture.get(i))
                .unwrap()
                .as_str()
                .trim();
            if let Some(id) = target.strip_prefix('#') {
                if !super::syntax::identifier(id) {
                    return fail("Invalid CSS fragment");
                }
                rewritten.push_str(&format!("url(#{id})"));
            } else {
                let name = self.resource(target, path.parent().unwrap_or(root), true)?;
                rewritten.push_str(&format!("url(\"{}\")", &name["assets/".len()..]));
            }
            offset = matched.end();
        }
        rewritten.push_str(&css[offset..]);
        self.insert(rewritten.into_bytes(), "css", "")
    }
}
