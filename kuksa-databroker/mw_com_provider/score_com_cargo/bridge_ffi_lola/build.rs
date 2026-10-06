use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

fn main() {
    println!("cargo:rerun-if-env-changed=SCORE_COM_BAZEL_BIN");
    println!("cargo:rerun-if-env-changed=SCORE_COM_LINK_PARAMS");
    println!("cargo:rerun-if-env-changed=SCORE_COM_VEHICLE_GEN_LIB_DIR");

    let Some(bazel_bin) = env::var_os("SCORE_COM_BAZEL_BIN").map(PathBuf::from) else {
        return;
    };

    if link_from_bazel_params(&bazel_bin) {
        println!("cargo:rustc-link-lib=dylib=stdc++");
        println!("cargo:rustc-link-lib=dylib=rt");
        println!("cargo:rustc-link-lib=dylib=atomic");
        println!("cargo:rustc-link-lib=dylib=acl");
        return;
    }

    require_link_dir(
        bazel_bin.join("score/mw/com/impl/rust/com-api/com-api-ffi-lola"),
        "registry_bridge_macro_cpp",
    );
    require_link_dir(vehicle_gen_dir(&bazel_bin), "vehicle_gen_cpp");

    println!("cargo:rustc-link-lib=dylib=registry_bridge_macro_cpp");
    println!("cargo:rustc-link-lib=dylib=vehicle_gen_cpp");
    println!("cargo:rustc-link-lib=dylib=stdc++");
}

fn link_from_bazel_params(bazel_bin: &Path) -> bool {
    let params_path = env::var_os("SCORE_COM_LINK_PARAMS")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            bazel_bin.join("score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example-0.params")
        });
    let Ok(params) = fs::read_to_string(&params_path) else {
        return false;
    };
    let Some(score_build_root) = bazel_bin.parent() else {
        return false;
    };

    println!("cargo:rerun-if-changed={}", params_path.display());
    link_dir(vehicle_gen_dir(bazel_bin));

    let mut alwayslink_archives = Vec::new();

    let mut lines = params.lines().map(str::trim).filter(|line| !line.is_empty()).peekable();
    while let Some(line) = lines.next() {
        if let Some(path) = line.strip_prefix("-Lnative=") {
            link_dir(score_build_root.join(path));
        } else if let Some(library) = line.strip_prefix("-lstatic=") {
            println!("cargo:rustc-link-lib=static={library}");
        } else if let Some(argument) = line.strip_prefix("-Clink-arg=") {
            if argument == "-Wl,--whole-archive" || argument == "-Wl,--no-whole-archive" {
                println!("cargo:rustc-link-arg={argument}");
            } else if argument.starts_with("bazel-out/") && argument.ends_with(".lo") {
                alwayslink_archives.push(score_build_root.join(argument));
            }
        } else if line == "-Clink-arg" {
            if let Some(argument) = lines.next() {
                if argument.starts_with("bazel-out/") && argument.ends_with(".lo") {
                    alwayslink_archives.push(score_build_root.join(argument));
                }
            }
        } else if let Some(argument) = line.strip_prefix("--codegen=link-arg=") {
            if matches!(argument, "-lpthread" | "-lrt" | "-lm" | "-ldl") {
                println!("cargo:rustc-link-arg={argument}");
            }
        }
    }

    if let Some(archive_path) = create_alwayslink_archive(&alwayslink_archives) {
        if let Some(archive_dir) = archive_path.parent() {
            link_dir(archive_dir.to_path_buf());
        }
        println!("cargo:rustc-link-lib=static:+whole-archive=score_com_alwayslink");
    }

    true
}

fn create_alwayslink_archive(archives: &[PathBuf]) -> Option<PathBuf> {
    if archives.is_empty() {
        return None;
    }

    let out_dir = env::var_os("OUT_DIR").map(PathBuf::from)?;
    let archive_path = out_dir.join("libscore_com_alwayslink.a");
    let _ = fs::remove_file(&archive_path);
    let mut script = format!("CREATE {}\n", archive_path.display());
    for (index, archive) in archives.iter().enumerate() {
        println!("cargo:rerun-if-changed={}", archive.display());
        let local_archive = out_dir.join(format!("score_com_alwayslink_part_{index}.a"));
        fs::copy(archive, &local_archive).ok()?;
        script.push_str(&format!("ADDLIB {}\n", local_archive.display()));
    }
    script.push_str("SAVE\nEND\n");

    let mut command = Command::new("ar")
        .arg("-M")
        .stdin(Stdio::piped())
        .spawn()
        .ok()?;
    command.stdin.as_mut()?.write_all(script.as_bytes()).ok()?;
    let status = command.wait().ok()?;
    status.success().then_some(archive_path)
}

fn vehicle_gen_dir(bazel_bin: &Path) -> PathBuf {
    env::var_os("SCORE_COM_VEHICLE_GEN_LIB_DIR").map(PathBuf::from).unwrap_or_else(|| {
        bazel_bin.join("score/mw/com/example/vehicle-dynamics-example/com-api-gen")
    })
}

fn link_dir(path: PathBuf) {
    println!("cargo:rustc-link-search=native={}", path.display());
}

fn require_link_dir(path: PathBuf, library: &str) {
    if !path.exists() {
        panic!(
            "S-Core Bazel output for {library} was not found at {}. Set SCORE_COM_BAZEL_BIN to the communication bazel-bin directory that contains built outputs, for example /mnt/c/Shares/ToRutuja/ToPrashanth/communication/New folder_generatedFilesAfterBuild/bazel-bin.",
            path.display()
        );
    }
    link_dir(path);
}