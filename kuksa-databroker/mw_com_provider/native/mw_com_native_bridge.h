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

#ifndef MW_COM_PROVIDER_NATIVE_MW_COM_NATIVE_BRIDGE_H
#define MW_COM_PROVIDER_NATIVE_MW_COM_NATIVE_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum MwComProviderNativeStatus
{
    MW_COM_PROVIDER_NATIVE_OK = 0,
    MW_COM_PROVIDER_NATIVE_ERROR = 1,
    MW_COM_PROVIDER_NATIVE_UNSUPPORTED = 2,
    MW_COM_PROVIDER_NATIVE_NO_SAMPLE = 3,
};

enum MwComProviderNativeValueKind
{
    MW_COM_PROVIDER_NATIVE_VALUE_BOOL = 0,
    MW_COM_PROVIDER_NATIVE_VALUE_STRING = 1,
    MW_COM_PROVIDER_NATIVE_VALUE_I64 = 2,
    MW_COM_PROVIDER_NATIVE_VALUE_U64 = 3,
    MW_COM_PROVIDER_NATIVE_VALUE_F64 = 4,
    MW_COM_PROVIDER_NATIVE_VALUE_BYTES = 5,
};

typedef struct MwComNativeTransportHandle MwComNativeTransportHandle;

typedef struct MwComNativeElementConfig
{
    const char* service_name;
    const char* instance_name;
    const char* member_name;
    const char* element_kind;
    const char* payload_type;
    size_t sample_size;
    size_t sample_alignment;
    uint8_t has_serialized_format;
} MwComNativeElementConfig;

typedef struct MwComNativeValue
{
    uint32_t kind;
    uint8_t bool_value;
    int64_t i64_value;
    uint64_t u64_value;
    double f64_value;
    const uint8_t* bytes_ptr;
    size_t bytes_len;
} MwComNativeValue;

typedef struct MwComNativeMessage
{
    const char* service_name;
    const char* instance_name;
    const char* member_name;
    MwComNativeValue value;
    uint8_t has_source_timestamp;
    uint64_t source_timestamp_nanos_since_epoch;
    uint32_t quality;
} MwComNativeMessage;

int32_t mw_com_provider_native_create(const MwComNativeElementConfig* elements,
                                   size_t element_count,
                                   MwComNativeTransportHandle** out_handle);

void mw_com_provider_native_destroy(MwComNativeTransportHandle* handle);

int32_t mw_com_provider_native_connect(MwComNativeTransportHandle* handle);

int32_t mw_com_provider_native_disconnect(MwComNativeTransportHandle* handle);

int32_t mw_com_provider_native_subscribe(MwComNativeTransportHandle* handle,
                                      const char* service_name,
                                      const char* instance_name,
                                      const char* member_name);

int32_t mw_com_provider_native_recv(MwComNativeTransportHandle* handle,
                                 uint32_t timeout_ms,
                                 MwComNativeMessage* out_message);

void mw_com_provider_native_release_message(MwComNativeTransportHandle* handle, MwComNativeMessage* message);

int32_t mw_com_provider_native_send_actuation(MwComNativeTransportHandle* handle, const MwComNativeMessage* message);

#ifdef __cplusplus
}
#endif

#endif