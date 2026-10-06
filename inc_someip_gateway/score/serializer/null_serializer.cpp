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

/// @file
/// This file provides a "serializer" which actually doesn't serialize and just copies the memory.

#include <csignal>
#include <cstddef>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <string_view>
#include <vector>

#include "score/config/mw_someip_config_generated.h"
#include "score/mw/log/logging.h"
#include "score/serializer/pre_serialized_data.h"
#include "score/serializer/serializer.h"

using score::someip_gateway::serializer::get_size_of_pre_serialized_data;
using score::someip_gateway::serializer::PreSerializedData;

// We don't know the actual size of the PreSerializedData struct at compile time because it depends
// on the max_message_size specified in the config, so we use a view with zero-sized array and
// calculate the size at runtime.
using PreSerializedDataView = PreSerializedData<0>;

enum class SerializerKind { Null, VehicleDynamics };

struct score_com_serializer {
    SerializerKind kind;
    const void* config;
};

struct VehicleDynamicsSample {
    double value;
    std::uint8_t quality;
};

static_assert(sizeof(VehicleDynamicsSample) == 16);
static_assert(alignof(VehicleDynamicsSample) == 8);
static_assert(offsetof(VehicleDynamicsSample, quality) == 8);

namespace {

/// Convert from opaque score_com_serializer pointer to NullSerializerConfig
const score::mw_someip_config::NullSerializerConfig* to_null_config(
    const struct score_com_serializer* serializer) {
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
    return static_cast<const score::mw_someip_config::NullSerializerConfig*>(serializer->config);
}

const score::mw_someip_config::VehicleDynamicsSerializerConfig* to_vehicle_dynamics_config(
    const struct score_com_serializer* serializer) {
    return static_cast<const score::mw_someip_config::VehicleDynamicsSerializerConfig*>(
        serializer->config);
}

std::vector<std::unique_ptr<score_com_serializer>>& serializer_handles() {
    static std::vector<std::unique_ptr<score_com_serializer>> handles;
    return handles;
}

std::mutex& serializer_handles_mutex() {
    static std::mutex mutex;
    return mutex;
}

const score_com_serializer* make_serializer_handle(SerializerKind kind, const void* config) {
    std::lock_guard lock(serializer_handles_mutex());
    for (const auto& handle : serializer_handles()) {
        if (handle->kind == kind && handle->config == config) {
            return handle.get();
        }
    }
    auto handle = std::make_unique<score_com_serializer>(score_com_serializer{kind, config});
    const auto* result = handle.get();
    serializer_handles().push_back(std::move(handle));
    return result;
}

std::shared_ptr<const score::mw_someip_config::Root>& get_config() {
    static std::shared_ptr<const score::mw_someip_config::Root> config;
    return config;
}

};  // anonymous namespace

score_com_serializer_result score_com_serializer_serialize(const struct score_com_serializer* serializer,
                                                           uint8_t* buffer, size_t buffer_size,
                                                           const void* object,
                                                           size_t* written_bytes) {
    if (serializer == nullptr || buffer == nullptr || object == nullptr) {
        return score_com_serializer_result_general_failure;
    }
    if (serializer->kind == SerializerKind::VehicleDynamics) {
        const auto payload_size = to_vehicle_dynamics_config(serializer)->max_payload_size();
        if (payload_size != 9 || buffer_size < payload_size) {
            return score_com_serializer_result_serialization_failure;
        }
        const auto* sample = static_cast<const VehicleDynamicsSample*>(object);
        std::memcpy(buffer, &sample->value, sizeof(sample->value));
        buffer[sizeof(sample->value)] = sample->quality;
        if (written_bytes != nullptr) {
            *written_bytes = payload_size;
        }
        return score_com_serializer_result_ok;
    }
    const auto* pre_serialized_data = static_cast<const PreSerializedDataView*>(object);
    std::size_t message_size = pre_serialized_data->size;
    if (message_size > buffer_size) {
        return score_com_serializer_result_serialization_failure;
    }
    std::memcpy(buffer, pre_serialized_data->data, message_size);
    if (written_bytes != nullptr) {
        *written_bytes = message_size;
    }
    return score_com_serializer_result_ok;
}

score_com_serializer_result score_com_serializer_deserialize(
    const struct score_com_serializer* serializer, const uint8_t* buffer, size_t buffer_size,
    void* object) {
    if (serializer == nullptr || buffer == nullptr || object == nullptr) {
        return score_com_serializer_result_general_failure;
    }
    if (serializer->kind == SerializerKind::VehicleDynamics) {
        const auto payload_size = to_vehicle_dynamics_config(serializer)->max_payload_size();
        if (payload_size != 9 || buffer_size != payload_size) {
            return score_com_serializer_result_deserialization_failure;
        }
        auto* sample = static_cast<VehicleDynamicsSample*>(object);
        std::memcpy(&sample->value, buffer, sizeof(sample->value));
        sample->quality = buffer[sizeof(sample->value)];
        return score_com_serializer_result_ok;
    }
    auto* pre_serialized_data = static_cast<PreSerializedDataView*>(object);
    if (buffer_size > to_null_config(serializer)->max_message_size()) {
        return score_com_serializer_result_deserialization_failure;
    }
    std::memcpy(pre_serialized_data->data, buffer, buffer_size);
    pre_serialized_data->size = buffer_size;
    return score_com_serializer_result_ok;
}

std::size_t score_com_serializer_get_max_serialized_size(
    const struct score_com_serializer* serializer) {
    if (serializer == nullptr) {
        return 0;
    }
    if (serializer->kind == SerializerKind::VehicleDynamics) {
        return to_vehicle_dynamics_config(serializer)->max_payload_size();
    }
    return to_null_config(serializer)->max_message_size();
}

std::size_t score_com_serializer_get_sizeof_type(const struct score_com_serializer* serializer) {
    if (serializer == nullptr) {
        return 0;
    }
    if (serializer->kind == SerializerKind::VehicleDynamics) {
        return sizeof(VehicleDynamicsSample);
    }
    return get_size_of_pre_serialized_data(to_null_config(serializer)->max_message_size());
}

std::size_t score_com_serializer_get_alignof_type(const struct score_com_serializer* serializer) {
    if (serializer == nullptr) {
        return 0;
    }
    if (serializer->kind == SerializerKind::VehicleDynamics) {
        return alignof(VehicleDynamicsSample);
    }
    return alignof(PreSerializedDataView);
}

score_com_serializer_result score_com_serializer_init(const char* serializer_identifier,
                                                      size_t serializer_identifier_size) {
    std::string_view serializer_id(serializer_identifier, serializer_identifier_size);

    // Read config data
    // TODO: Use memory mapped file instead of copying into buffer
    std::ifstream config_file;
    config_file.open(std::string(serializer_id), std::ios::binary | std::ios::in);

    if (!config_file.is_open()) {
        score::mw::log::LogError() << "Error: Could not open config file " << serializer_id;
        return score_com_serializer_result_serializer_nonexistent;
    }

    config_file.seekg(0, std::ios::end);
    std::streampos length = config_file.tellg();

    if (length <= 0) {
        score::mw::log::LogError()
            << "Error: Invalid config file size: " << static_cast<std::size_t>(length);
        config_file.close();
        return score_com_serializer_result_serializer_nonexistent;
    }

    config_file.seekg(0, std::ios::beg);
    auto config_buffer = std::shared_ptr<char[]>(new char[length]);
    config_file.read(config_buffer.get(), length);
    config_file.close();

    get_config() = std::shared_ptr<const score::mw_someip_config::Root>(
        config_buffer, score::mw_someip_config::GetRoot(config_buffer.get()));

    return score_com_serializer_result_ok;
}

score_com_serializer_result score_com_serializer_deinit() {
    get_config().reset();
    std::lock_guard lock(serializer_handles_mutex());
    serializer_handles().clear();
    return score_com_serializer_result_ok;
}

namespace {

const score_com_serializer* lookup_serializer(
    std::string_view service_type_name, score_com_serializer_element_type element_type,
    std::string_view element_name) {
    const auto config = get_config();
    if (config == nullptr || config->service_types() == nullptr) {
        return nullptr;
    }

    for (const auto* service_type : *config->service_types()) {
        if (service_type->service_type_name() == nullptr ||
            service_type->service_type_name()->string_view() != service_type_name) {
            continue;
        }

        if (element_type == score_com_serializer_element_type_event) {
            if (service_type->events() == nullptr) {
                return nullptr;
            }
            for (const auto* event : *service_type->events()) {
                if (event->event_name() != nullptr &&
                    event->event_name()->string_view() == element_name) {
                    if (event->serialization_config_type() ==
                        score::mw_someip_config::SerializationConfig_NullSerializerConfig) {
                        const auto* config = event->serialization_config_as_NullSerializerConfig();
                        return config == nullptr
                                   ? nullptr
                                   : make_serializer_handle(SerializerKind::Null, config);
                    }
                    if (event->serialization_config_type() ==
                        score::mw_someip_config::SerializationConfig_VehicleDynamicsSerializerConfig) {
                        const auto* config =
                            event->serialization_config_as_VehicleDynamicsSerializerConfig();
                        return config == nullptr
                                   ? nullptr
                                   : make_serializer_handle(SerializerKind::VehicleDynamics,
                                                            config);
                    }
                    return nullptr;
                }
            }
        } else if (element_type == score_com_serializer_element_type_method_call) {
            if (service_type->methods() == nullptr) {
                return nullptr;
            }
            for (const auto* method : *service_type->methods()) {
                if (method->method_name() != nullptr &&
                    method->method_name()->string_view() == element_name) {
                    const auto* config =
                        method->request_serialization_config_as_NullSerializerConfig();
                    return config == nullptr ? nullptr
                                             : make_serializer_handle(SerializerKind::Null, config);
                }
            }
        } else if (element_type == score_com_serializer_element_type_method_response) {
            if (service_type->methods() == nullptr) {
                return nullptr;
            }
            for (const auto* method : *service_type->methods()) {
                if (method->method_name() != nullptr &&
                    method->method_name()->string_view() == element_name) {
                    const auto* config =
                        method->response_serialization_config_as_NullSerializerConfig();
                    return config == nullptr ? nullptr
                                             : make_serializer_handle(SerializerKind::Null, config);
                }
            }
        }

        return nullptr;
    }

    return nullptr;
}

}  // namespace

score_com_serializer_result score_com_serializer_get(
    const char* service_type, size_t service_type_size,
    enum score_com_serializer_element_type element_type, const char* element_name,
    size_t element_name_size, const struct score_com_serializer** serializer) {
    if (serializer == nullptr) {
        return score_com_serializer_result_general_failure;
    }

    std::string_view service_type_name(service_type, service_type_size);
    std::string_view element_name_view(element_name, element_name_size);

    const auto* serializer_handle =
        lookup_serializer(service_type_name, element_type, element_name_view);
    if (serializer_handle == nullptr) {
        score::mw::log::LogError()
            << "Error: No serialization config found for service_type=" << service_type_name
            << " element=" << element_name_view;
        return score_com_serializer_result_serializer_nonexistent;
    }

    *serializer = serializer_handle;

    return score_com_serializer_result_ok;
}
