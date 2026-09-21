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

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "score/mw/com/runtime.h"
#include "score/mw/com/types.h"
#include "score/serializer/pre_serialized_data.h"

namespace {

constexpr std::string_view kDefaultConfigurationPath{"score/gatewayd/etc/mw_com_config.json"};
constexpr std::string_view kInstanceSpecifier{"gatewayd/tire_pressure"};
constexpr std::string_view kEventName{"tire_pressure"};
constexpr std::size_t kMaxSampleCount{4U};
constexpr std::chrono::seconds kWaitTimeout{15};

enum class CompletionState {
    kPending,
    kSucceeded,
    kFailed,
};

enum class FailureReason {
    kNone,
    kInvalidInstanceSpecifier,
    kDiscoveryFailed,
    kNoServiceHandle,
    kProxyCreationFailed,
    kMissingEvent,
    kReceiveHandlerFailed,
    kSubscribeFailed,
    kNoSamplesDelivered,
    kGetNewSamplesFailed,
    kTimeout,
};

const char* ToString(const FailureReason reason) {
    switch (reason) {
        case FailureReason::kNone:
            return "no failure";
        case FailureReason::kInvalidInstanceSpecifier:
            return "invalid instance specifier";
        case FailureReason::kDiscoveryFailed:
            return "service discovery failed";
        case FailureReason::kNoServiceHandle:
            return "service discovery returned no handles";
        case FailureReason::kProxyCreationFailed:
            return "GenericProxy::Create failed";
        case FailureReason::kMissingEvent:
            return "event tire_pressure not found in GenericProxy";
        case FailureReason::kReceiveHandlerFailed:
            return "SetReceiveHandler failed";
        case FailureReason::kSubscribeFailed:
            return "Subscribe failed";
        case FailureReason::kNoSamplesDelivered:
            return "receive handler ran but GetNewSamples delivered no samples";
        case FailureReason::kGetNewSamplesFailed:
            return "GetNewSamples failed";
        case FailureReason::kTimeout:
            return "timed out waiting for tire_pressure sample";
    }
    return "unknown failure";
}

std::string ResolveConfigurationPath(const std::string& path) {
    const auto file_exists = [](const std::string& candidate) {
        return std::filesystem::exists(std::filesystem::path{candidate});
    };

    if (file_exists(path)) {
        return path;
    }

    std::vector<std::string> candidates{};
    const auto append_from_env = [&candidates, &path](const char* env_var_name) {
        const char* root = std::getenv(env_var_name);
        if ((root == nullptr) || (root[0] == '\0')) {
            return;
        }

        const std::string runfiles_root{root};
        candidates.emplace_back(runfiles_root + "/_main/" + path);
        candidates.emplace_back(runfiles_root + "/" + path);
    };

    append_from_env("TEST_SRCDIR");
    append_from_env("RUNFILES_DIR");

    for (const auto& candidate : candidates) {
        if (file_exists(candidate)) {
            return candidate;
        }
    }

    return path;
}

}  // namespace

class TirePressureConsumer {
   public:
    explicit TirePressureConsumer(std::string configuration_path)
        : configuration_path_{std::move(configuration_path)} {}

    int Run() {
        const std::string resolved_configuration_path =
            ResolveConfigurationPath(configuration_path_);
        if (!std::filesystem::exists(std::filesystem::path{resolved_configuration_path})) {
            std::cerr << "Failed to locate runtime configuration file '" << configuration_path_
                      << "'. Also checked Bazel runfiles paths via TEST_SRCDIR/RUNFILES_DIR."
                      << std::endl;
            return EXIT_FAILURE;
        }

        if (resolved_configuration_path != configuration_path_) {
            std::cout << "Resolved runtime configuration path from '" << configuration_path_
                      << "' to '" << resolved_configuration_path << "'." << std::endl;
        }

        std::cout << "Initializing mw::com runtime from " << resolved_configuration_path
                  << std::endl;
        score::mw::com::runtime::InitializeRuntime(
            score::mw::com::runtime::RuntimeConfiguration{resolved_configuration_path});

        const auto instance_specifier_result =
            score::mw::com::InstanceSpecifier::Create(std::string{kInstanceSpecifier});
        if (!instance_specifier_result.has_value()) {
            std::cerr << "Failed to create instance specifier '" << kInstanceSpecifier
                      << "': " << instance_specifier_result.error() << std::endl;
            return EXIT_FAILURE;
        }

        const auto start_find_result = score::mw::com::GenericProxy::StartFindService(
            [this](score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
                   score::mw::com::FindServiceHandle find_handle) noexcept {
                OnServiceAvailable(std::move(handles), find_handle);
            },
            instance_specifier_result.value());

        if (!start_find_result.has_value()) {
            std::cerr << "Failed to start discovery for '" << kInstanceSpecifier
                      << "': " << start_find_result.error() << std::endl;
            return EXIT_FAILURE;
        }

        {
            std::unique_lock<std::mutex> lock{mutex_};
            if (!completion_cv_.wait_for(lock, kWaitTimeout,
                                         [this] { return state_ != CompletionState::kPending; })) {
                state_ = CompletionState::kFailed;
                failure_reason_ = FailureReason::kTimeout;
            }
        }

        CompletionState completion_state{CompletionState::kPending};
        FailureReason failure_reason{FailureReason::kNone};
        std::optional<score::mw::com::FindServiceHandle> find_service_handle;
        {
            std::lock_guard<std::mutex> lock{mutex_};
            completion_state = state_;
            failure_reason = failure_reason_;
            find_service_handle = find_service_handle_;
        }

        if (find_service_handle.has_value()) {
            (void)score::mw::com::GenericProxy::StopFindService(find_service_handle.value());
        }
        Cleanup();
        if (completion_state == CompletionState::kFailed) {
            std::cerr << "Tire-pressure consumer failed: " << ToString(failure_reason) << std::endl;
            return EXIT_FAILURE;
        }

        std::cout << "Tire-pressure consumer completed after receiving " << received_samples_.load()
                  << " sample(s)." << std::endl;
        return EXIT_SUCCESS;
    }

   private:
    void OnServiceAvailable(
        score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
        score::mw::com::FindServiceHandle find_handle) noexcept {
        (void)score::mw::com::GenericProxy::StopFindService(find_handle);

        if (handles.empty()) {
            MarkFailure(FailureReason::kNoServiceHandle);
            return;
        }

        {
            std::lock_guard<std::mutex> lock{mutex_};
            find_service_handle_ = find_handle;
        }

        std::cout << "Found gatewayd/tire_pressure, creating GenericProxy." << std::endl;
        auto proxy_result = score::mw::com::GenericProxy::Create(handles.front());
        if (!proxy_result.has_value()) {
            std::cerr << "Failed to create GenericProxy for '" << kInstanceSpecifier
                      << "': " << proxy_result.error() << std::endl;
            MarkFailure(FailureReason::kProxyCreationFailed);
            return;
        }

        proxy_.emplace(std::move(proxy_result).value());
        auto events = proxy_->GetEvents();
        const auto event_it = events.find(kEventName);
        if (event_it == events.cend()) {
            std::cerr << "GenericProxy does not expose event '" << kEventName << "'." << std::endl;
            MarkFailure(FailureReason::kMissingEvent);
            return;
        }

        tire_pressure_event_ = &event_it->second;
        std::cout << "Discovered event '" << kEventName
                  << "' (sample size: " << tire_pressure_event_->GetSampleSize() << ", serialized: "
                  << (tire_pressure_event_->HasSerializedFormat() ? "true" : "false") << ")."
                  << std::endl;

        const auto receive_handler_result =
            tire_pressure_event_->SetReceiveHandler([this]() noexcept { OnReceive(); });
        if (!receive_handler_result.has_value()) {
            std::cerr << "Failed to set receive handler for '" << kEventName
                      << "': " << receive_handler_result.error() << std::endl;
            MarkFailure(FailureReason::kReceiveHandlerFailed);
            return;
        }

        const auto subscribe_result = tire_pressure_event_->Subscribe(kMaxSampleCount);
        if (!subscribe_result.has_value()) {
            std::cerr << "Failed to subscribe to '" << kEventName
                      << "': " << subscribe_result.error() << std::endl;
            MarkFailure(FailureReason::kSubscribeFailed);
            return;
        }

        std::cout << "Subscribed to '" << kEventName << "' and waiting for the first sample."
                  << std::endl;
    }

    void OnReceive() noexcept {
        if (tire_pressure_event_ == nullptr) {
            MarkFailure(FailureReason::kMissingEvent);
            return;
        }

        bool saw_sample{false};
        const auto get_new_samples_result = tire_pressure_event_->GetNewSamples(
            [this, &saw_sample](score::mw::com::SamplePtr<void> sample) noexcept {
                saw_sample = true;
                const std::size_t sample_number =
                    received_samples_.fetch_add(1U, std::memory_order_relaxed) + 1U;

                using PreSerializedDataView =
                    score::someip_gateway::serializer::PreSerializedData<0>;
                const auto* const raw_sample =
                    static_cast<const PreSerializedDataView*>(sample.Get());

                std::ostringstream hex_bytes;
                std::uint8_t pressure_value{0U};
                if (raw_sample != nullptr) {
                    for (std::size_t i = 0U; i < raw_sample->size; ++i) {
                        hex_bytes << std::hex << std::setw(2) << std::setfill('0')
                                  << std::to_integer<int>(raw_sample->data[i]) << ' ';
                    }
                    if (raw_sample->size > 0U) {
                        pressure_value =
                            std::to_integer<std::uint8_t>(raw_sample->data[raw_sample->size - 1U]);
                    }
                }

                std::cout << "Received tire_pressure sample #" << sample_number
                          << " (sample size: " << tire_pressure_event_->GetSampleSize()
                          << ", serialized: "
                          << (tire_pressure_event_->HasSerializedFormat() ? "true" : "false") << ")"
                          << ": pressure=" << static_cast<int>(pressure_value)
                          << " payload=" << hex_bytes.str() << std::dec << std::endl;
            },
            kMaxSampleCount);

        if (!get_new_samples_result.has_value()) {
            std::cerr << "Failed to drain samples from '" << kEventName
                      << "': " << get_new_samples_result.error() << std::endl;
            MarkFailure(FailureReason::kGetNewSamplesFailed);
            return;
        }

        if (!saw_sample) {
            std::cout << "Receive handler invoked without a new sample." << std::endl;
            return;
        }

        MarkSuccess();
    }

    void MarkSuccess() noexcept {
        {
            std::lock_guard<std::mutex> lock{mutex_};
            if (state_ != CompletionState::kPending) {
                return;
            }
            state_ = CompletionState::kSucceeded;
        }
        completion_cv_.notify_one();
    }

    void MarkFailure(const FailureReason reason) noexcept {
        {
            std::lock_guard<std::mutex> lock{mutex_};
            if (state_ != CompletionState::kPending) {
                return;
            }
            state_ = CompletionState::kFailed;
            failure_reason_ = reason;
        }
        completion_cv_.notify_one();
    }

    void Cleanup() noexcept {
        if (tire_pressure_event_ == nullptr) {
            return;
        }

        const auto unset_result = tire_pressure_event_->UnsetReceiveHandler();

        if (!unset_result.has_value()) {
            std::cerr << "UnsetReceiveHandler failed: " << unset_result.error() << std::endl;
        }

        tire_pressure_event_->Unsubscribe();
        tire_pressure_event_ = nullptr;
    }

    std::string configuration_path_;
    std::mutex mutex_;
    std::condition_variable completion_cv_;
    CompletionState state_{CompletionState::kPending};
    FailureReason failure_reason_{FailureReason::kNone};
    std::optional<score::mw::com::FindServiceHandle> find_service_handle_;
    std::optional<score::mw::com::GenericProxy> proxy_;
    score::mw::com::GenericProxyEvent* tire_pressure_event_{nullptr};
    std::atomic<std::size_t> received_samples_{0U};
};

int main(int argc, char* argv[]) {
    std::string configuration_path{std::string{kDefaultConfigurationPath}};
    for (int index = 1; index < argc; ++index) {
        const std::string_view argument{argv[index]};
        if ((argument == "--configuration") && ((index + 1) < argc)) {
            configuration_path = argv[++index];
        }
    }

    TirePressureConsumer consumer{std::move(configuration_path)};
    return consumer.Run();
}
