//! Standalone CLI for the experimental Rust engine; no Python required.
//! Differences from Python 0.11 are intentionally documented.

use sedrava_core::navigation::run_session_from;
use sedrava_core::runtime::resolve;
use sedrava_core::snapshot::{restore_snapshot, serialize_state};
use sedrava_core::{parse, run_tests, Error, Result};
use serde_json::json;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

fn usage() {
    println!(
        "Sedrava native Rust core (EXPERIMENTAL)\n\
         Usage:\n\
           sedrava-native lock DIR\n           sedrava-native verify DIR\n           sedrava-native database check FILE\n           sedrava-native database run FILE --database ABSOLUTE_FILE --trusted [--arg NAME=JSON ...] [--allow-write --request-key KEY]\n           sedrava-native host check FILE
           sedrava-native host run FILE --root DIR --trusted [--allow-read] [--allow-write]
           sedrava-native server check FILE
           sedrava-native server run FILE [--port PORT] [--max-requests N] [--idle-ms N] [--state-dir ABSOLUTE_PRIVATE_DIR] [--transactional] [--journaled] [--sqlite-state FILE] [--sqlite-v2-state FILE] [--native-index FILE --native-index-sha256 SHA256] [--native-log FILE [--native-max-bytes N --native-max-transactions N]]
           sedrava-native check FILE\n\
           sedrava-native effects FILE [--target app|web|android]\n\
           sedrava-native test FILE\n\
           sedrava-native run FILE [ACTION ...] [--state-file PATH]\n\
           sedrava-native inspect FILE
           sedrava-native ir FILE
           sedrava-native ir-candidate FILE
           sedrava-native expand FILE
           sedrava-native build web FILE [--output PATH]
           sedrava-native build web-ir FILE [--output PATH]
           sedrava-native build site FILE --output DIR
           sedrava-native build webapp FILE --output DIR
           sedrava-native build android FILE --output DIR --application-id ID\n\
         Supports typed records, bounded lists, pure functions, navigation,\n\
         snapshot persistence and experimental typed IR export.\n\
         Full Site/WebApp and Android generators remain incomplete.
         Native Android preview requires explicit application ID.
         WebApp HTTP uses same-origin capabilities. Native Host supports trusted local text/JSON files and scoped directories.\n\
         See docs/RUST_FULL_MIGRATION.ru.md. Do not use for production."
    );
}

fn source_dir(source: &str) -> &Path {
    Path::new(source)
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
}

fn read_source(path: &str) -> Result<String> {
    let max_bytes = (sedrava_core::model::MAX_SOURCE_CHARS as u64) * 4;
    let read_error = |err| Error(format!("Cannot read {path}: {err}"));
    let metadata = fs::metadata(path).map_err(read_error)?;
    if !metadata.is_file() || metadata.len() > max_bytes {
        return Err(Error(
            "Source must be a regular file within the size limit".into(),
        ));
    }
    let mut raw = String::new();
    fs::File::open(path)
        .map_err(read_error)?
        .take(max_bytes + 1)
        .read_to_string(&mut raw)
        .map_err(read_error)?;
    if raw.len() as u64 > max_bytes {
        return Err(Error("Source file exceeds size limit".into()));
    }
    Ok(raw)
}

#[cfg(any(target_os = "linux", target_vendor = "apple"))]
fn publish_new_directory(staged: &Path, output: &Path) -> std::io::Result<()> {
    use rustix::fs::{renameat_with, RenameFlags, CWD};
    renameat_with(CWD, staged, CWD, output, RenameFlags::NOREPLACE)?;
    Ok(())
}

#[cfg(not(any(target_os = "linux", target_vendor = "apple")))]
fn publish_new_directory(staged: &Path, output: &Path) -> std::io::Result<()> {
    match fs::symlink_metadata(output) {
        Ok(_) => Err(std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            "Output already exists",
        )),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => fs::rename(staged, output),
        Err(e) => Err(e),
    }
}

fn load(path: &str) -> Result<sedrava_core::Program> {
    let metadata = fs::metadata(path).map_err(|e| Error(format!("Cannot stat {path}: {e}")))?;
    if metadata.len() > (sedrava_core::model::MAX_SOURCE_CHARS as u64) * 4 {
        return Err(Error("Source file exceeds size limit".into()));
    }
    let expanded = sedrava_core::modules::expand_local_imports(Path::new(path))?;
    parse(&expanded.source)
}

/// Persist after successfully validating every action. No in-place truncation.
fn write_snapshot(path: &Path, raw: &str) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)
        .map_err(|e| Error(format!("Cannot create snapshot directory: {e}")))?;
    let mut temp = tempfile::NamedTempFile::new_in(parent)
        .map_err(|e| Error(format!("Cannot prepare temporary snapshot: {e}")))?;
    temp.write_all(raw.as_bytes())
        .map_err(|e| Error(format!("Cannot write snapshot: {e}")))?;
    temp.flush()
        .map_err(|e| Error(format!("Cannot flush snapshot: {e}")))?;
    temp.as_file()
        .sync_all()
        .map_err(|e| Error(format!("Cannot sync snapshot: {e}")))?;
    temp.persist(path)
        .map_err(|e| Error(format!("Cannot atomically replace snapshot: {e}")))?;
    // Directory sync is supported on Unix but not universally on Windows.
    #[cfg(unix)]
    {
        let dir = fs::File::open(parent)
            .map_err(|e| Error(format!("Cannot open snapshot directory for sync: {e}")))?;
        dir.sync_all()
            .map_err(|e| Error(format!("Cannot sync snapshot directory: {e}")))?;
    }
    Ok(())
}

fn read_snapshot(path: &Path) -> Result<String> {
    let meta = fs::metadata(path).map_err(|e| Error(format!("Cannot stat snapshot: {e}")))?;
    if meta.len() > 800_000 {
        return Err(Error("Snapshot file too large".into()));
    }
    fs::read_to_string(path).map_err(|e| Error(format!("Cannot read snapshot: {e}")))
}

/// The Python CLI accepts --state-file before or after the action list.
fn run_options(args: &[String]) -> Result<(Vec<String>, Option<PathBuf>)> {
    let mut actions = Vec::new();
    let mut state_file = None;
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--state-file" {
            if state_file.is_some() || index + 1 >= args.len() {
                return Err(Error("Expected exactly one --state-file PATH".into()));
            }
            state_file = Some(PathBuf::from(&args[index + 1]));
            index += 2;
        } else {
            if args[index].starts_with("--") {
                return Err(Error(format!("Unknown run option: {}", args[index])));
            }
            actions.push(args[index].clone());
            index += 1;
        }
    }
    Ok((actions, state_file))
}

#[cfg(unix)]
fn host_command(args: &[String]) -> Result<()> {
    use sedrava_core::host::{self, Outcome, Policy, Status};
    if let [command, source] = args {
        if command == "check" {
            host::parse(&read_source(source)?)?;
            println!("OK: {source} (native Host)");
            return Ok(());
        }
    }
    if args.first().map(String::as_str) != Some("run") {
        return Err(Error(
            "Expected host check FILE or host run FILE with an explicit policy".into(),
        ));
    }
    let outcome = (|| {
        let (source, options) = args.get(1..)?.split_first()?;
        let mut policy = Policy::new(PathBuf::new());
        let mut supplied = Vec::new();
        let mut seen = std::collections::BTreeSet::new();
        let mut options = options.iter();
        while let Some(flag) = options.next() {
            if flag != "--arg" && !seen.insert(flag) {
                return None;
            }
            match flag.as_str() {
                "--root" => policy.root = PathBuf::from(options.next()?),
                "--trusted" => policy.trusted = true,
                "--allow-read" => policy.allow_read = true,
                "--allow-write" => policy.allow_write = true,
                "--allow-list" => policy.allow_list = true,
                "--allow-mkdir" => policy.allow_mkdir = true,
                "--allow-rmdir" => policy.allow_rmdir = true,
                "--read-scope" => policy.read_scope = options.next()?.clone(),
                "--write-scope" => policy.write_scope = options.next()?.clone(),
                "--list-scope" => policy.list_scope = options.next()?.clone(),
                "--arg" if supplied.len() < 16 => supplied.push(options.next()?.clone()),
                "--result-protocol" if options.next()?.as_str() == "v1" => {}
                _ => return None,
            }
        }
        if policy.root.as_os_str().is_empty() {
            return None;
        }
        let program = host::parse(&read_source(source).ok()?).ok()?;
        Some(host::run(&program, &policy, &supplied))
    })()
    .unwrap_or_else(Outcome::rejected);
    let raw = serde_json::to_string(&outcome).map_err(|e| Error(e.to_string()))?;
    writeln!(std::io::stdout().lock(), "{raw}")
        .map_err(|e| Error(format!("Cannot deliver Host result: {e}")))?;
    if outcome.status == Status::Success {
        Ok(())
    } else {
        Err(Error(
            "Host execution did not succeed; see the v1 outcome".into(),
        ))
    }
}

#[cfg(not(unix))]
fn host_command(_args: &[String]) -> Result<()> {
    Err(Error(
        "Native Host execution requires POSIX descriptor-relative filesystem APIs".into(),
    ))
}

fn server_command(args: &[String]) -> Result<()> {
    use sedrava_core::server::{self, RuntimeOptions};
    match args {
        [command, source] if command == "check" => {
            let program = server::parse(&read_source(source)?)?;
            println!("OK: server {} (native, loopback-only)", program.name);
            Ok(())
        }
        [command, source, options @ ..] if command == "run" => {
            let program = server::parse(&read_source(source)?)?;
            let mut settings=RuntimeOptions {
                port: 0,
                max_requests: 32,
                idle_ms: 30_000,
            };
            let mut state_dir=None;
            let mut transactional=false;
            let mut journaled=false;
            let mut sqlite_state=None;
            let mut sqlite_v2_state=None;
            let mut native_index=None;
            let mut native_log=None;
            let mut native_max_bytes=None;
            let mut native_max_transactions=None;
            let mut native_index_sha=None;
            let mut seen=std::collections::BTreeSet::new();
            let mut next=options.iter();
            while let Some(flag)=next.next() {
                if !seen.insert(flag.as_str()) {
                    return Err(Error("E_SERVER_CLI: duplicated option".into()));
                }
                if flag=="--transactional" {
                    transactional=true;
                    continue;
                }
                if flag=="--journaled" {
                    journaled=true;
                    continue;
                }
                let value=next.next().ok_or_else(|| Error(
                    "E_SERVER_CLI: expected option argument".into()))?;
                match flag.as_str() {
                    "--port" => settings.port=value.parse::<u16>()
                        .map_err(|_|Error("E_SERVER_CLI: invalid port".into()))?,
                    "--max-requests" => settings.max_requests=value.parse::<u32>()
                        .map_err(|_|Error("E_SERVER_CLI: invalid max-requests".into()))?,
                    "--idle-ms" => settings.idle_ms=value.parse::<u32>()
                        .map_err(|_|Error("E_SERVER_CLI: invalid idle-ms".into()))?,
                     "--state-dir" => state_dir=Some(PathBuf::from(value)),
                    "--sqlite-state" => sqlite_state=Some(PathBuf::from(value)),
                    "--sqlite-v2-state" => sqlite_v2_state=Some(PathBuf::from(value)),
                    "--native-log" => native_log=Some(PathBuf::from(value)),
                    "--native-max-bytes" => native_max_bytes=Some(value.parse::<u64>().map_err(|_|Error("E_SERVER_CLI: invalid native byte limit".into()))?),
                    "--native-max-transactions" => native_max_transactions=Some(value.parse::<u64>().map_err(|_|Error("E_SERVER_CLI: invalid native transaction limit".into()))?),
                    "--native-index" => native_index=Some(PathBuf::from(value)),
                    "--native-index-sha256" => native_index_sha=Some(value.as_str()),
                    _ => return Err(Error(format!("E_SERVER_CLI: unsupported option {flag}"))),
                }
            }
            let native = match (native_index.as_deref(), native_index_sha) {
                (Some(path), Some(sha)) => Some((path, sha)),
                (None, None) => None,
                _ => return Err(Error("E_SERVER_NATIVE_INDEX: both native index flags required".into())),
            };
            let limits = match (native_max_bytes,native_max_transactions) {
                (None,None) => sedravasql::native_log::NativeLimits::default(),
                (Some(max_bytes),Some(max_transactions)) if native_log.is_some() => sedravasql::native_log::NativeLimits {max_bytes,max_transactions},
                _ => return Err(Error("E_SERVER_NATIVE_LOG: both limit flags and native log required".into())),
            };
            server::serve_with_native_limits(&program,settings,state_dir.as_deref(),transactional,journaled,sqlite_state.as_deref(),sqlite_v2_state.as_deref(),native,native_log.as_deref(),limits)
        }
        _ => Err(Error("Expected server check FILE or server run FILE [--port PORT] [--max-requests N] [--idle-ms N] [--state-dir ABSOLUTE_PRIVATE_DIR] [--transactional] [--journaled] [--sqlite-state FILE] [--sqlite-v2-state FILE] [--native-index FILE --native-index-sha256 SHA256] [--native-log FILE [--native-max-bytes N --native-max-transactions N]]".into())),
    }
}

fn database_command(args:&[String])->Result<()> {
    use sedrava_core::database;
    match args {
        [cmd,source] if cmd=="check"=>{
            let program=database::parse(&read_source(source)?)?;
            println!("OK: database {} (native SQL host)",program.name);
            Ok(())
        }
        [cmd,source,rest @ ..] if cmd=="run"=>{
            let program=database::parse(&read_source(source)?)?;
            let mut path=None;let mut trusted=false;let mut write=false;let mut key=None;
            let mut supplied=Vec::new();let mut seen=std::collections::BTreeSet::new();let mut it=rest.iter();
            while let Some(flag)=it.next(){
                if flag!="--arg"&&!seen.insert(flag.as_str()){return Err(Error("E_DATABASE_CLI: duplicate option".into()));}
                match flag.as_str(){
                    "--trusted"=>trusted=true,
                    "--allow-write"=>write=true,
                    "--database"=>path=it.next().map(PathBuf::from),
                    "--request-key"=>key=it.next().map(String::as_str),
                    "--arg" if supplied.len()<32=>supplied.push(it.next().ok_or_else(||Error("E_DATABASE_CLI: missing argument".into()))?.clone()),
                    _=>return Err(Error("E_DATABASE_CLI: invalid option".into())),
                }
            }
            let path=path.ok_or_else(||Error("E_DATABASE_CLI: database path required".into()))?;
            let result=database::run(&program,&path,trusted,write,key,&supplied)?;
            println!("{}",serde_json::to_string(&result).map_err(|e|Error(e.to_string()))?);
            Ok(())
        }
        _=>Err(Error("Expected database check FILE or database run FILE with explicit policy".into()))
    }
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() == 1 || args.get(1).is_some_and(|s| s == "--help" || s == "-h") {
        usage();
        return Ok(());
    }
    if args[1] == "--version" {
        println!(
            "sedrava-native {} (experimental native preview; not stable)",
            env!("CARGO_PKG_VERSION")
        );
        return Ok(());
    }
    if args.len() < 3 {
        usage();
        return Err(Error("Expected a command and a .sdr file".into()));
    }
    let command = &args[1];
    if command == "database" { return database_command(&args[2..]); }
    if command == "host" {
        return host_command(&args[2..]);
    }
    if command == "server" {
        return server_command(&args[2..]);
    }
    if command == "lock" || command == "verify" {
        if args.len() != 3 {
            return Err(Error("Expected lock DIR or verify DIR".into()));
        }
        let root = Path::new(&args[2]);
        if command == "lock" {
            let file = sedrava_core::packages::write_lock(root)?;
            println!("Created verified lock: {}", file.display());
        } else {
            let paths = sedrava_core::packages::verify(root)?;
            println!("Verified lock: {} pinned files", paths.len());
        }
        return Ok(());
    }
    if command == "effects" {
        let target = match args.as_slice() {
            [_, _, _, flag, target] if flag == "--target" => target.as_str(),
            [_, _, _] => "app",
            _ => {
                return Err(Error(
                    "Expected effects FILE [--target app|web|android]".into(),
                ))
            }
        };
        if !matches!(target, "app" | "web" | "android") {
            return Err(Error(
                "Unsupported effects CLI target (app|web|android)".into(),
            ));
        }
        let source = Path::new(&args[2]);
        // Import expansion and locked-vendor SHA verification precede hashing.
        let expanded = sedrava_core::modules::expand_local_imports(source)?;
        // Python 0.12 canonical app-domain expansion terminates with one LF.
        // Keep this behavior for byte-identical source_sha256 manifests without
        // altering legacy Rust module expansion used by other commands.
        let canonical = format!("{}\n", expanded.source.trim_end_matches('\n'));
        let checked = parse(&canonical)?;
        let manifest = sedrava_core::effects::manifest(&checked, &canonical, target)?;
        println!("{}", sedrava_core::effects::canonical_json(&manifest)?);
        return Ok(());
    }
    let is_build = command == "build";
    if is_build
        && !matches!(
            args.get(2).map(String::as_str),
            Some("web" | "web-ir" | "android" | "site" | "webapp")
        )
    {
        return Err(Error(
            "Native build supports only experimental web, site, webapp and android targets".into(),
        ));
    }
    let source_index = if is_build { 3 } else { 2 };
    let source = args
        .get(source_index)
        .ok_or_else(|| Error("Expected a command, target and .sdr file".into()))?;
    // An explicit project manifest always requires an intact reviewed lock,
    // including for Site/WebApp that currently use a separate module parser.
    sedrava_core::packages::verify_if_project(Path::new(source))?;
    if is_build && matches!(args[2].as_str(), "site" | "webapp") {
        if args.len() != 6 || args[4] != "--output" {
            return Err(Error(format!(
                "Expected build {} FILE --output DIR",
                args[2]
            )));
        }
        let output = PathBuf::from(&args[5]);
        if fs::symlink_metadata(&output).is_ok() {
            return Err(Error("Web output directory must not already exist".into()));
        }
        let raw = read_source(source)?;
        let root = Some(source_dir(source));
        let site = if args[2] == "webapp" {
            sedrava_core::site::webapp::generate(&raw, root)?
        } else {
            sedrava_core::site::generate_at(&raw, root)?
        };
        let parent = output
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        fs::create_dir_all(parent)
            .map_err(|e| Error(format!("Cannot create output parent: {e}")))?;
        let staging = tempfile::tempdir_in(parent)
            .map_err(|e| Error(format!("Cannot stage Web directory: {e}")))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(staging.path(), fs::Permissions::from_mode(0o755))
                .map_err(|e| Error(format!("Cannot set Web directory permissions: {e}")))?;
        }
        for (name, content) in &site.files {
            let relative = Path::new(name);
            if relative.is_absolute()
                || relative
                    .components()
                    .any(|part| !matches!(part, std::path::Component::Normal(_)))
            {
                return Err(Error("Unsafe generated Web path".into()));
            }
            let target = staging.path().join(relative);
            let mut directory = staging.path().to_path_buf();
            if let Some(relative_parent) = relative.parent() {
                for component in relative_parent.components() {
                    directory.push(component);
                    fs::create_dir_all(&directory)
                        .map_err(|e| Error(format!("Cannot create Web subdirectory: {e}")))?;
                    #[cfg(unix)]
                    {
                        use std::os::unix::fs::PermissionsExt;
                        fs::set_permissions(&directory, fs::Permissions::from_mode(0o755))
                            .map_err(|e| {
                                Error(format!("Cannot set Web subdirectory permissions: {e}"))
                            })?;
                    }
                }
            }
            fs::write(&target, content)
                .map_err(|e| Error(format!("Cannot write Web file: {e}")))?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&target, fs::Permissions::from_mode(0o644))
                    .map_err(|e| Error(format!("Cannot set Web file permissions: {e}")))?;
            }
        }
        let temp = staging.keep();
        if let Err(e) = publish_new_directory(&temp, &output) {
            let _ = fs::remove_dir_all(&temp);
            return Err(Error(format!("Cannot publish Web directory: {e}")));
        }
        println!("{}", output.display());
        return Ok(());
    }
    if is_build && args[2] == "android" {
        if args.len() != 8 || args[4] != "--output" || args[6] != "--application-id" {
            return Err(Error(
                "Expected build android FILE --output DIR --application-id ID".into(),
            ));
        }
        let output = PathBuf::from(&args[5]);
        if fs::symlink_metadata(&output).is_ok() {
            return Err(Error(
                "Android output directory must not already exist".into(),
            ));
        }
        let program = load(source)?;
        let project = sedrava_core::android::generate(&program, &args[7])?;
        let parent = output
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        fs::create_dir_all(parent)
            .map_err(|e| Error(format!("Cannot create output parent: {e}")))?;
        let staging = tempfile::tempdir_in(parent)
            .map_err(|e| Error(format!("Cannot stage Android project: {e}")))?;
        for (name, bytes) in &project.files {
            let relative = Path::new(name);
            if relative.is_absolute()
                || relative
                    .components()
                    .any(|part| !matches!(part, std::path::Component::Normal(_)))
            {
                return Err(Error("Invalid generated relative Android path".into()));
            }
            let target = staging.path().join(relative);
            let dir = target
                .parent()
                .ok_or_else(|| Error("Generated project path missing parent".into()))?;
            fs::create_dir_all(dir)
                .map_err(|e| Error(format!("Cannot stage Android directory: {e}")))?;
            fs::write(&target, bytes)
                .map_err(|e| Error(format!("Cannot write Android source: {e}")))?;
        }
        let temp = staging.keep();
        if let Err(error) = publish_new_directory(&temp, &output) {
            let _ = fs::remove_dir_all(&temp);
            return Err(Error(format!(
                "Cannot atomically publish Android directory: {error}"
            )));
        }
        println!("{}", output.display());
        return Ok(());
    }
    if is_build {
        let output = if args.len() == 4 {
            PathBuf::from("build/web/index.html")
        } else if args.len() == 6 && args[4] == "--output" {
            PathBuf::from(&args[5])
        } else {
            return Err(Error("Expected build web FILE [--output PATH]".into()));
        };
        let expanded = sedrava_core::modules::expand_local_imports(Path::new(source))?;
        let program = parse(&expanded.source)?;
        let generated = if args[2] == "web-ir" {
            let candidate = sedrava_core::ir_candidate::export(&program)?;
            sedrava_core::web_ir::generate(&candidate)?
        } else {
            sedrava_core::web::generate_web(&program)?
        };
        let source_path = fs::canonicalize(source).map_err(|e| Error(e.to_string()))?;
        let parent = output
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        let parent_real = if parent.exists() {
            fs::canonicalize(parent).map_err(|e| Error(e.to_string()))?
        } else {
            fs::create_dir_all(parent).map_err(|e| Error(e.to_string()))?;
            fs::canonicalize(parent).map_err(|e| Error(e.to_string()))?
        };
        let file_name = output
            .file_name()
            .ok_or_else(|| Error("Build output must be a file".into()))?;
        let output_canonical = parent_real.join(file_name);
        if output_canonical == source_path || expanded.imported_paths.contains(&output_canonical) {
            return Err(Error(
                "Web output must not overwrite the source or an imported module".into(),
            ));
        }
        write_snapshot(&output, &generated)?;
        // Snapshots deliberately use private tempfile permissions. Generated
        // static web artifacts, in contrast, must be readable by web servers.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&output, fs::Permissions::from_mode(0o644))
                .map_err(|e| Error(format!("Cannot make generated web output readable: {e}")))?;
        }
        println!("{}", output.display());
        return Ok(());
    }
    if command == "expand" && args.len() == 3 {
        let expanded = sedrava_core::modules::expand_local_imports(Path::new(source))?;
        print!("{}", expanded.source);
        return Ok(());
    }
    // Use the matching presentation generator to check native Web sources and assets.
    if command == "check" && args.len() == 3 {
        let raw = read_source(source)?;
        let mode = raw
            .lines()
            .map(str::trim)
            .find(|s| !s.is_empty() && !s.starts_with('#'))
            .and_then(|line| line.split_whitespace().next());
        let root = Some(source_dir(source));
        match mode {
            Some("site") => {
                sedrava_core::site::generate_at(&raw, root)?;
            }
            Some("webapp") => {
                sedrava_core::site::webapp::generate(&raw, root)?;
            }
            _ => {}
        }
        if matches!(mode, Some("site" | "webapp")) {
            println!("OK: {source} (experimental native {})", mode.unwrap());
            return Ok(());
        }
    }
    let program = load(source)?;
    match command.as_str() {
        "check" if args.len() == 3 => {
            println!("OK: {source}");
        }
        "test" if args.len() == 3 => {
            println!("PASS: {} Sedrava tests", run_tests(&program)?);
        }
        "run" => {
            let (actions, state_file) = run_options(&args[3..])?;
            if let Some(path) = state_file.as_deref() {
                if path.exists() && fs::canonicalize(path).ok() == fs::canonicalize(source).ok() {
                    return Err(Error("Snapshot must differ from source file".into()));
                }
            }
            let initial = if let Some(path) = state_file.as_deref().filter(|path| path.exists()) {
                restore_snapshot(&program, &read_snapshot(path)?)?
            } else {
                program.states.clone()
            };
            let (final_state, output) = if program.has_navigation {
                let (state, stack) = run_session_from(&program, &initial, &actions)?;
                let values = resolve(&program, &state)?;
                let result = json!({"state":values,"stack":stack});
                (state, result)
            } else {
                let mut state = initial;
                for action in &actions {
                    let (next, accepted) = sedrava_core::transition(&program, &state, action)?;
                    if !accepted {
                        return Err(Error(format!(
                            "Action {action}: invariant rejected; state unchanged"
                        )));
                    }
                    state = next;
                }
                let result = serde_json::to_value(resolve(&program, &state)?)
                    .map_err(|e| Error(e.to_string()))?;
                (state, result)
            };
            if let Some(path) = state_file.as_deref() {
                // Serialization occurs before any filesystem write.
                let snapshot = serialize_state(&program, &final_state)?;
                write_snapshot(path, &snapshot)?;
            }
            println!(
                "{}",
                serde_json::to_string(&output).map_err(|e| Error(e.to_string()))?
            );
        }
        "ir" if args.len() == 3 => {
            let ir = sedrava_core::ir::export(&program)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&ir).map_err(|e| Error(e.to_string()))?
            );
        }
        "ir-candidate" if args.len() == 3 => {
            let ir = sedrava_core::ir_candidate::export(&program)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&ir).map_err(|e| Error(e.to_string()))?
            );
        }
        "inspect" if args.len() == 3 => {
            let output = json!({
                "engine": "rust-native-experimental",
                "project": program.name,
                "state_types": program.types,
                "actions": program.actions.keys().cloned().collect::<Vec<_>>(),
                "embedded_tests": program.tests.iter().map(|t| &t.name).collect::<Vec<_>>(),
                 "supported": "int32/bool/text, records, bounded lists, pure functions, queries, derives, rules, actions, tests, navigation",
                "full_language": false
            });
            println!(
                "{}",
                serde_json::to_string_pretty(&output).map_err(|e| Error(e.to_string()))?
            );
        }
        _ => {
            usage();
            return Err(Error(format!(
                "Unknown command or extra arguments: {command}"
            )));
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("error: {error}");
        std::process::exit(1);
    }
}
