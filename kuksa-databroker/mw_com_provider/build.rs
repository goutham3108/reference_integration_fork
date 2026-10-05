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
use std::path::PathBuf;

const DEFAULT_GENERATED_METADATA: &str = "generated/mw_com_provider_metadata.rs";

fn main() {
    println!("cargo:rerun-if-env-changed=MW_COM_PROVIDER_METADATA_RS");
    println!("cargo:rerun-if-env-changed=MW_COM_ROOT");
    println!("cargo:rerun-if-env-changed=MW_COM_NATIVE_INCLUDE_DIRS");
    println!("cargo:rerun-if-env-changed=MW_COM_NATIVE_LIB_DIR");
    println!("cargo:rerun-if-env-changed=MW_COM_NATIVE_LIBS");
    println!("cargo:rerun-if-env-changed=MW_COM_NATIVE_BUILD_BRIDGE");

    configure_mw_com_native_bridge();
    copy_generated_metadata();
}

fn copy_generated_metadata() {
    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR must be set by Cargo"));
    let generated_file = out_dir.join("mw_com_generated.rs");
    let metadata_path = env::var("MW_COM_PROVIDER_METADATA_RS")
        .unwrap_or_else(|_| DEFAULT_GENERATED_METADATA.to_string());

    println!("cargo:rerun-if-changed={metadata_path}");

    let content = fs::read_to_string(&metadata_path).unwrap_or_else(|_| default_metadata());
    fs::write(generated_file, content).expect("failed to write generated mw::com metadata");
}

fn default_metadata() -> String {
    r#"/********************************************************************************
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

pub const MW_COM_SERVICE_DEFS: &str = "unset";
pub const MW_COM_BINDINGS_AVAILABLE: bool = false;

pub fn describe_generated_bindings() -> &'static str {
    ""
}

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub struct GeneratedStructFieldAccessor {
    pub struct_name: &'static str,
    pub field_name: &'static str,
    pub datatype: &'static str,
    pub size: usize,
    pub alignment: usize,
}

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub struct GenericMwComElement {
    pub service_name: &'static str,
    pub instance_name: &'static str,
    pub instance_specifier: &'static str,
    pub member_name: &'static str,
    pub element_kind: &'static str,
    pub payload_type: &'static str,
    pub sample_size: usize,
    pub sample_alignment: usize,
    pub has_serialized_format: bool,
}

pub const GENERATED_STRUCT_FIELD_ACCESSORS: &[GeneratedStructFieldAccessor] = &[];
pub const GENERATED_GENERIC_MW_COM_ELEMENTS: &[GenericMwComElement] = &[];

pub fn find_struct_field_accessor(
    struct_name: &str,
    field_name: &str,
) -> Option<&'static GeneratedStructFieldAccessor> {
    GENERATED_STRUCT_FIELD_ACCESSORS
        .iter()
        .find(|accessor| accessor.struct_name == struct_name && accessor.field_name == field_name)
}

pub fn find_generic_mw_com_element(
    service_name: &str,
    instance_name: &str,
    member_name: &str,
) -> Option<&'static GenericMwComElement> {
    GENERATED_GENERIC_MW_COM_ELEMENTS.iter().find(|element| {
        element.service_name == service_name
            && (element.instance_name == instance_name || element.instance_specifier == instance_name)
            && element.member_name == member_name
    })
}
"#
    .to_string()
}

fn configure_mw_com_native_bridge() {
    if env::var_os("CARGO_FEATURE_MW_COM_NATIVE").is_none() {
        return;
    }

    if let Ok(lib_dir) = env::var("MW_COM_NATIVE_LIB_DIR") {
        println!("cargo:rustc-link-search=native={lib_dir}");
    }

    if let Ok(libs) = env::var("MW_COM_NATIVE_LIBS") {
        for lib in libs.split(',').map(str::trim).filter(|lib| !lib.is_empty()) {
            println!("cargo:rustc-link-lib={lib}");
        }
    }

    if env::var("MW_COM_NATIVE_BUILD_BRIDGE").as_deref() != Ok("1") {
        return;
    }

    let mut build = cc::Build::new();
    build.cpp(true).std("c++17");
    build.file("native/mw_com_native_bridge.cpp");
    build.include("native");

    if let Ok(root) = env::var("MW_COM_ROOT") {
        build.include(root);
    }

    if let Ok(include_dirs) = env::var("MW_COM_NATIVE_INCLUDE_DIRS") {
        for include_dir in include_dirs
            .split(':')
            .map(str::trim)
            .filter(|include_dir| !include_dir.is_empty())
        {
            build.include(include_dir);
        }
    }

    build.compile("mw_com_provider_native_bridge");
}
