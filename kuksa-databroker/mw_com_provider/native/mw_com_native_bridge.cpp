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

#include "mw_com_native_bridge.h"

#include <memory>
#include <string>
#include <vector>

struct MwComNativeTransportHandle
{
    std::vector<MwComNativeElementConfig> elements{};
    std::vector<std::string> strings{};
};

namespace
{
bool IsNull(const char* value) noexcept
{
    return value == nullptr;
}
}  // namespace

int32_t mw_com_provider_native_create(const MwComNativeElementConfig* elements,
                                   const size_t element_count,
                                   MwComNativeTransportHandle** out_handle)
{
    if (out_handle == nullptr || (elements == nullptr && element_count != 0U))
    {
        return MW_COM_PROVIDER_NATIVE_ERROR;
    }

    auto handle = std::make_unique<MwComNativeTransportHandle>();
    handle->elements.reserve(element_count);
    handle->strings.reserve(element_count * 5U);

    for (size_t i = 0; i < element_count; ++i)
    {
        const auto& input = elements[i];
        if (IsNull(input.service_name) || IsNull(input.instance_name) || IsNull(input.member_name) ||
            IsNull(input.element_kind) || IsNull(input.payload_type))
        {
            return MW_COM_PROVIDER_NATIVE_ERROR;
        }

        handle->strings.emplace_back(input.service_name);
        const char* service_name = handle->strings.back().c_str();
        handle->strings.emplace_back(input.instance_name);
        const char* instance_name = handle->strings.back().c_str();
        handle->strings.emplace_back(input.member_name);
        const char* member_name = handle->strings.back().c_str();
        handle->strings.emplace_back(input.element_kind);
        const char* element_kind = handle->strings.back().c_str();
        handle->strings.emplace_back(input.payload_type);
        const char* payload_type = handle->strings.back().c_str();

        handle->elements.push_back(MwComNativeElementConfig{service_name,
                                                         instance_name,
                                                         member_name,
                                                         element_kind,
                                                         payload_type,
                                                         input.sample_size,
                                                         input.sample_alignment,
                                                         input.has_serialized_format});
    }

    *out_handle = handle.release();
    return MW_COM_PROVIDER_NATIVE_OK;
}

void mw_com_provider_native_destroy(MwComNativeTransportHandle* handle)
{
    delete handle;
}

int32_t mw_com_provider_native_connect(MwComNativeTransportHandle* handle)
{
    if (handle == nullptr)
    {
        return MW_COM_PROVIDER_NATIVE_ERROR;
    }

    return MW_COM_PROVIDER_NATIVE_UNSUPPORTED;
}

int32_t mw_com_provider_native_disconnect(MwComNativeTransportHandle* handle)
{
    if (handle == nullptr)
    {
        return MW_COM_PROVIDER_NATIVE_ERROR;
    }

    return MW_COM_PROVIDER_NATIVE_OK;
}

int32_t mw_com_provider_native_subscribe(MwComNativeTransportHandle* handle,
                                      const char* service_name,
                                      const char* instance_name,
                                      const char* member_name)
{
    if (handle == nullptr || IsNull(service_name) || IsNull(instance_name) || IsNull(member_name))
    {
        return MW_COM_PROVIDER_NATIVE_ERROR;
    }

    return MW_COM_PROVIDER_NATIVE_UNSUPPORTED;
}

int32_t mw_com_provider_native_recv(MwComNativeTransportHandle* handle, const uint32_t, MwComNativeMessage* out_message)
{
    if (handle == nullptr || out_message == nullptr)
    {
        return MW_COM_PROVIDER_NATIVE_ERROR;
    }

    return MW_COM_PROVIDER_NATIVE_NO_SAMPLE;
}

void mw_com_provider_native_release_message(MwComNativeTransportHandle*, MwComNativeMessage*) {}

int32_t mw_com_provider_native_send_actuation(MwComNativeTransportHandle* handle, const MwComNativeMessage* message)
{
    if (handle == nullptr || message == nullptr)
    {
        return MW_COM_PROVIDER_NATIVE_ERROR;
    }

    return MW_COM_PROVIDER_NATIVE_UNSUPPORTED;
}