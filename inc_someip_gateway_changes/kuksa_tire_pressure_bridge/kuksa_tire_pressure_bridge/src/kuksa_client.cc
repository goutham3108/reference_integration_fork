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

#include "kuksa_client.h"

#include <chrono>
#include <iostream>
#include <mutex>
#include <utility>

#include <grpcpp/grpcpp.h>
#include "kuksa/val/v1/val.grpc.pb.h"

namespace score::integration {

namespace {

kuksa::val::v1::Datapoint MakeUint16Datapoint(std::uint16_t value) {
    kuksa::val::v1::Datapoint datapoint;

    const auto now = std::chrono::system_clock::now();
    const auto seconds =
        std::chrono::time_point_cast<std::chrono::seconds>(now);
    const auto nanos =
        std::chrono::duration_cast<std::chrono::nanoseconds>(now - seconds);

    datapoint.mutable_timestamp()->set_seconds(seconds.time_since_epoch().count());
    datapoint.mutable_timestamp()->set_nanos(static_cast<int>(nanos.count()));
    datapoint.set_uint32(value);

    return datapoint;
}

kuksa::val::v1::Datapoint MakeBoolDatapoint(bool value) {
    kuksa::val::v1::Datapoint datapoint;

    const auto now = std::chrono::system_clock::now();
    const auto seconds = std::chrono::time_point_cast<std::chrono::seconds>(now);
    const auto nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(now - seconds);

    datapoint.mutable_timestamp()->set_seconds(seconds.time_since_epoch().count());
    datapoint.mutable_timestamp()->set_nanos(static_cast<int>(nanos.count()));
    datapoint.set_bool_(value);

    return datapoint;
}

bool ExtractFloat(const kuksa::val::v1::Datapoint& datapoint, float* output) {
    if (output == nullptr) {
        return false;
    }

    switch (datapoint.value_case()) {
        case kuksa::val::v1::Datapoint::kFloat:
            *output = datapoint.float_();
            return true;
        case kuksa::val::v1::Datapoint::kDouble:
            *output = static_cast<float>(datapoint.double_());
            return true;
        case kuksa::val::v1::Datapoint::kUint32:
            *output = static_cast<float>(datapoint.uint32());
            return true;
        default:
            return false;
    }
}

bool ExtractBool(const kuksa::val::v1::Datapoint& datapoint, bool* output) {
    if (output == nullptr || datapoint.value_case() != kuksa::val::v1::Datapoint::kBool) {
        return false;
    }
    *output = datapoint.bool_();
    return true;
}

}  // namespace

struct KuksaValV1Client::Impl {
    explicit Impl(std::string endpoint_in)
        : endpoint(std::move(endpoint_in)) {}

    std::string endpoint;
    std::shared_ptr<grpc::Channel> channel;
    std::unique_ptr<kuksa::val::v1::VAL::Stub> stub;

    std::atomic_bool stop_requested{false};
    std::mutex threads_mutex;
    std::vector<std::thread> subscription_threads;
};

KuksaValV1Client::KuksaValV1Client(std::string endpoint)
    : impl_(std::make_unique<Impl>(std::move(endpoint))) {}

KuksaValV1Client::~KuksaValV1Client() {
    Stop();
}

bool KuksaValV1Client::Connect() {
    impl_->channel = grpc::CreateChannel(
        impl_->endpoint, grpc::InsecureChannelCredentials());
    impl_->stub = kuksa::val::v1::VAL::NewStub(impl_->channel);

    const auto deadline =
        std::chrono::system_clock::now() + std::chrono::seconds(3);

    if (!impl_->channel->WaitForConnected(deadline)) {
        std::cerr << "KUKSA: failed to connect to " << impl_->endpoint << '\n';
        return false;
    }

    std::cout << "KUKSA: connected to " << impl_->endpoint << '\n';
    return true;
}

bool KuksaValV1Client::PublishBool(std::string_view signal_path, bool value) {
    if (!impl_->stub) {
        std::cerr << "KUKSA: PublishBool called before Connect()\n";
        return false;
    }

    kuksa::val::v1::SetRequest request;
    auto* update = request.add_updates();
    update->mutable_entry()->set_path(std::string(signal_path));
    *update->mutable_entry()->mutable_actuator_target() = MakeBoolDatapoint(value);
    update->add_fields(kuksa::val::v1::FIELD_ACTUATOR_TARGET);

    kuksa::val::v1::SetResponse response;
    grpc::ClientContext context;
    const grpc::Status status = impl_->stub->Set(&context, request, &response);
    if (!status.ok() || response.errors_size() != 0) {
        std::cerr << "KUKSA Set failed for " << signal_path
                  << ": code=" << status.error_code()
                  << " message=" << status.error_message() << '\n';
        return false;
    }
    return true;
}

bool KuksaValV1Client::PublishUint16(
    std::string_view signal_path,
    std::uint16_t value) {

    if (!impl_->stub) {
        std::cerr << "KUKSA: PublishUint16 called before Connect()\n";
        return false;
    }

    kuksa::val::v1::SetRequest request;
    auto* update = request.add_updates();
    update->mutable_entry()->set_path(std::string(signal_path));
    *update->mutable_entry()->mutable_value() = MakeUint16Datapoint(value);
    update->add_fields(kuksa::val::v1::FIELD_VALUE);

    kuksa::val::v1::SetResponse response;
    grpc::ClientContext context;

    const grpc::Status status =
        impl_->stub->Set(&context, request, &response);

    if (!status.ok() || response.errors_size() != 0) {
        std::cerr << "KUKSA Set failed for " << signal_path
                  << ": code=" << status.error_code()
                  << " message=" << status.error_message() << '\n';
        return false;
    }

    return true;
}

bool KuksaValV1Client::SubscribeFloat(
    std::string signal_path,
    FloatCallback callback) {

    if (!impl_->stub) {
        std::cerr << "KUKSA: SubscribeFloat called before Connect()\n";
        return false;
    }

    std::lock_guard<std::mutex> lock(impl_->threads_mutex);

    impl_->subscription_threads.emplace_back(
        [this, signal_path = std::move(signal_path),
         callback = std::move(callback)]() mutable {

            while (!impl_->stop_requested.load()) {
                grpc::ClientContext context;
                kuksa::val::v1::SubscribeRequest request;
                auto* entry = request.add_entries();
                entry->set_path(signal_path);
                entry->set_view(kuksa::val::v1::VIEW_CURRENT_VALUE);
                entry->add_fields(kuksa::val::v1::FIELD_VALUE);

                auto reader = impl_->stub->Subscribe(&context, request);
                kuksa::val::v1::SubscribeResponse response;

                while (!impl_->stop_requested.load() &&
                       reader->Read(&response)) {
                    for (const auto& update : response.updates()) {
                        if (update.entry().path() != signal_path ||
                            !update.entry().has_value()) {
                            continue;
                        }
                        float value = 0.0F;
                        if (ExtractFloat(update.entry().value(), &value)) {
                            callback(value);
                        }
                    }
                }

                const grpc::Status status = reader->Finish();

                if (impl_->stop_requested.load()) {
                    break;
                }

                std::cerr << "KUKSA subscription ended for "
                          << signal_path << ": "
                          << status.error_message()
                          << ". Retrying in 1 second.\n";

                std::this_thread::sleep_for(std::chrono::seconds(1));
            }
        });

    return true;
}

bool KuksaValV1Client::SubscribeBool(
    std::string signal_path,
    BoolCallback callback) {

    if (!impl_->stub) {
        std::cerr << "KUKSA: SubscribeBool called before Connect()\n";
        return false;
    }

    std::lock_guard<std::mutex> lock(impl_->threads_mutex);

    impl_->subscription_threads.emplace_back(
        [this, signal_path = std::move(signal_path),
         callback = std::move(callback)]() mutable {
            while (!impl_->stop_requested.load()) {
                grpc::ClientContext context;
                kuksa::val::v1::SubscribeRequest request;
                auto* entry = request.add_entries();
                entry->set_path(signal_path);
                entry->set_view(kuksa::val::v1::VIEW_CURRENT_VALUE);
                entry->add_fields(kuksa::val::v1::FIELD_VALUE);

                auto reader = impl_->stub->Subscribe(&context, request);
                kuksa::val::v1::SubscribeResponse response;

                while (!impl_->stop_requested.load() && reader->Read(&response)) {
                    for (const auto& update : response.updates()) {
                        if (update.entry().path() != signal_path || !update.entry().has_value()) {
                            continue;
                        }
                        bool value = false;
                        if (ExtractBool(update.entry().value(), &value)) {
                            callback(value);
                        }
                    }
                }

                const grpc::Status status = reader->Finish();
                if (impl_->stop_requested.load()) {
                    break;
                }
                std::cerr << "KUKSA subscription ended for " << signal_path << ": "
                          << status.error_message() << ". Retrying in 1 second.\n";
                std::this_thread::sleep_for(std::chrono::seconds(1));
            }
        });

    return true;
}

void KuksaValV1Client::Stop() {
    if (!impl_) {
        return;
    }

    impl_->stop_requested.store(true);

    std::lock_guard<std::mutex> lock(impl_->threads_mutex);
    for (auto& thread : impl_->subscription_threads) {
        if (thread.joinable()) {
            thread.join();
        }
    }
    impl_->subscription_threads.clear();
}

}  // namespace score::integration
