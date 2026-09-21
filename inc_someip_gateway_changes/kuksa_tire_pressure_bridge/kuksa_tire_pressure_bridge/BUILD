# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

cc_library(
    name = "bridge_core",
    srcs = [
        "src/tire_pressure_bridge.cc",
    ],
    hdrs = [
        "include/kuksa_client.h",
        "include/tire_pressure_bridge.h",
        "include/tire_pressure_types.h",
    ],
    includes = ["include"],
    visibility = ["//visibility:public"],
)

cc_library(
    name = "kuksa_client",
    srcs = ["src/kuksa_client.cc"],
    hdrs = ["include/kuksa_client.h"],
    includes = ["include"],
    deps = [
        "@grpc//:grpc++",
        "@kuksa_proto//:kuksa_val_v1_cc_grpc",
    ],
)

cc_library(
    name = "mw_com_adapter",
    srcs = ["src/mw_com_tire_pressure_adapter.cc"],
    hdrs = ["include/mw_com_tire_pressure_adapter.h"],
    includes = ["include"],
    deps = [
        ":bridge_core",
        "//score/serializer:pre_serialized_data",
        "@score_communication//score/mw/com",
    ],
)

cc_library(
    name = "mw_com_kuksa_publisher",
    srcs = ["src/mw_com_kuksa_publisher.cc"],
    hdrs = ["include/mw_com_kuksa_publisher.h"],
    includes = ["include"],
    deps = [
        ":bridge_core",
        "//score/serializer:pre_serialized_data",
        "@score_communication//score/mw/com",
    ],
)

cc_binary(
    name = "kuksa_tire_pressure_bridge",
    srcs = ["src/main.cc"],
    data = ["//score/gatewayd:etc/mw_com_config.json"],
    visibility = ["//visibility:public"],
    deps = [
        ":bridge_core",
        ":kuksa_client",
        ":mw_com_adapter",
        ":mw_com_kuksa_publisher",
        "@score_communication//score/mw/com",
    ],
)
