# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************

# Local copy of the generated mw::com interface binding.
#
# We cannot depend directly on
# @score_communication//score/mw/com/example/com-api-example/com-api-gen: that
# target is only visible to //score/mw/com:__subpackages__ inside the
# communication repository.

load("@rules_cc//cc:defs.bzl", "cc_library")
load("@rules_rust//rust:defs.bzl", "rust_library")

cc_library(
    name = "vehicle_gen_cpp",
    srcs = ["vehicle_gen.cpp"],
    hdrs = ["vehicle_gen.h"],
    implementation_deps = [
        "@score_communication//score/mw/com/rust/score_com_cpp_bridge:register_interface",
    ],
    alwayslink = True,
    visibility = ["//demo/mw_com_setup:__subpackages__"],
)

rust_library(
    name = "vehicle_gen",
    srcs = ["com_api_gen.rs"],
    crate_name = "kuksa_vehicle_gen",
    features = ["link_std_cpp_lib"],
    visibility = ["//demo/mw_com_setup:__subpackages__"],
    deps = [
        ":vehicle_gen_cpp",
        "@score_communication//score/mw/com/rust:score_com",
    ],
)
