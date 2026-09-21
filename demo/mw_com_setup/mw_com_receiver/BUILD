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

load("@rules_rust//rust:defs.bzl", "rust_binary")

rust_binary(
    name = "mw_com_receiver",
    srcs = ["main.rs"],
    data = ["//demo/mw_com_setup/kuksa_to_com:etc/mw_com_config.json"],
    features = ["link_std_cpp_lib"],
    deps = [
        "//demo/mw_com_setup/kuksa_to_com/gen:vehicle_gen",
        "@score_communication//score/mw/com/rust:score_com",
    ],
)
