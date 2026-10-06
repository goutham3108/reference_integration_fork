/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const DEFAULT_SCORE_COM_BAZEL_BIN: &str =
    "/mnt/c/Shares/ToRutuja/ToPrashanth/communication/New folder_generatedFilesAfterBuild/bazel-bin";

fn main() {
    println!("cargo:rerun-if-env-changed=SCORE_COM_BAZEL_BIN");
    println!("cargo:rerun-if-env-changed=SCORE_COM_VEHICLE_GEN_LIB_DIR");

    let bazel_bin = env::var_os("SCORE_COM_BAZEL_BIN")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_SCORE_COM_BAZEL_BIN));

    let bridge_dir = bazel_bin.join("score/mw/com/impl/rust/com-api/com-api-ffi-lola");
    let vehicle_gen_dir = vehicle_gen_dir(&bazel_bin);

    require_library_with_extensions(&bridge_dir, "registry_bridge_macro_cpp", &["a", "so"]);
    require_library_with_extensions(&vehicle_gen_dir, "vehicle_gen_cpp", &["lo", "a", "so"]);

    println!("cargo:rustc-link-search=native={}", bridge_dir.display());
    println!("cargo:rustc-link-search=native={}", vehicle_gen_dir.display());
    link_from_bazel_params(&bazel_bin);

    println!("cargo:rustc-link-lib=dylib=stdc++");
    println!("cargo:rustc-link-lib=dylib=rt");
    println!("cargo:rustc-link-lib=dylib=atomic");
    println!("cargo:rustc-link-lib=dylib=acl");
}

fn link_from_bazel_params(bazel_bin: &Path) {
    let params_path = env::var_os("SCORE_COM_LINK_PARAMS")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            bazel_bin.join("score/mw/com/example/vehicle-dynamics-example/vehicle-dynamics-example-0.params")
        });
    let params = fs::read_to_string(&params_path).unwrap_or_else(|error| {
        panic!(
            "failed to read S-Core link params from {}: {error}",
            params_path.display()
        )
    });
    let score_build_root = bazel_bin
        .parent()
        .expect("SCORE_COM_BAZEL_BIN must have a parent directory");

    println!("cargo:rerun-if-changed={}", params_path.display());

    let mut alwayslink_archives = Vec::new();
    let mut lines = params.lines().map(str::trim).filter(|line| !line.is_empty()).peekable();
    while let Some(line) = lines.next() {
        if let Some(path) = line.strip_prefix("-Lnative=") {
            println!(
                "cargo:rustc-link-search=native={}",
                score_build_root.join(path).display()
            );
        } else if let Some(library) = line.strip_prefix("-lstatic=") {
            println!("cargo:rustc-link-lib=static={library}");
        } else if let Some(argument) = line.strip_prefix("-Clink-arg=") {
            handle_link_arg(score_build_root, argument, &mut alwayslink_archives);
        } else if line == "-Clink-arg" {
            if let Some(argument) = lines.next() {
                handle_link_arg(score_build_root, argument, &mut alwayslink_archives);
            }
        } else if let Some(argument) = line.strip_prefix("--codegen=link-arg=") {
            if matches!(argument, "-lpthread" | "-lrt" | "-lm" | "-ldl" | "-lstdc++") {
                println!("cargo:rustc-link-arg={argument}");
            }
        }
    }

    if let Some(archive_path) = create_alwayslink_archive(&alwayslink_archives) {
        if let Some(archive_dir) = archive_path.parent() {
            println!("cargo:rustc-link-search=native={}", archive_dir.display());
        }
        println!("cargo:rustc-link-lib=static:+whole-archive=score_com_alwayslink");
    }
}

fn handle_link_arg(score_build_root: &Path, argument: &str, alwayslink_archives: &mut Vec<PathBuf>) {
    if argument == "-Wl,--whole-archive" || argument == "-Wl,--no-whole-archive" {
        println!("cargo:rustc-link-arg={argument}");
    } else if argument.starts_with("bazel-out/") && argument.ends_with(".lo") {
        alwayslink_archives.push(score_build_root.join(argument));
    }
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
    env::var_os("SCORE_COM_VEHICLE_GEN_LIB_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            bazel_bin.join("score/mw/com/example/vehicle-dynamics-example/com-api-gen")
        })
}

fn require_library_with_extensions(dir: &Path, library: &str, extensions: &[&str]) -> PathBuf {
    library_path(dir, library, extensions).unwrap_or_else(|| {
        panic!(
            "S-Core Bazel library {library} was not found in {}. Set SCORE_COM_BAZEL_BIN to the communication bazel-bin directory that contains built outputs.",
            dir.display()
        )
    })
}

fn library_path(dir: &Path, library: &str, extensions: &[&str]) -> Option<PathBuf> {
    extensions
        .iter()
        .map(|extension| dir.join(format!("lib{library}.{extension}")))
        .find(|path| path.exists())
}
