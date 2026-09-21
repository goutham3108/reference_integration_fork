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
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "score/mw/com/runtime.h"
#include "score/mw/com/types.h"
#include "score/serializer/pre_serialized_data.h"

namespace {

constexpr std::string_view kDefaultConfigurationPath{"score/gatewayd/etc/mw_com_config.json"};
constexpr std::string_view kInstanceSpecifier{"gatewayd/headlight"};
constexpr std::string_view kEventName{"headlight"};
constexpr std::size_t kMaxSampleCount{4U};
constexpr std::chrono::seconds kWaitTimeout{15};

std::string ResolveConfigurationPath(const std::string& path) {
    if (std::filesystem::exists(path)) {
        return path;
    }
    for (const char* variable : {"TEST_SRCDIR", "RUNFILES_DIR"}) {
        const char* const root = std::getenv(variable);
        if (root == nullptr || root[0] == '\0') {
            continue;
        }
        const std::string candidate = std::string{root} + "/_main/" + path;
        if (std::filesystem::exists(candidate)) {
            return candidate;
        }
    }
    return path;
}

}  // namespace

class HeadlightConsumer {
   public:
    explicit HeadlightConsumer(std::string configuration_path)
        : configuration_path_{std::move(configuration_path)} {}

    int Run() {
        const std::string resolved_path = ResolveConfigurationPath(configuration_path_);
        if (!std::filesystem::exists(resolved_path)) {
            std::cerr << "Failed to locate runtime configuration file '" << configuration_path_
                      << "'." << std::endl;
            return EXIT_FAILURE;
        }

        score::mw::com::runtime::InitializeRuntime(
            score::mw::com::runtime::RuntimeConfiguration{resolved_path});
        const auto instance = score::mw::com::InstanceSpecifier::Create(std::string{kInstanceSpecifier});
        if (!instance.has_value()) {
            std::cerr << "Failed to create instance specifier: " << instance.error() << std::endl;
            return EXIT_FAILURE;
        }

        const auto find_result = score::mw::com::GenericProxy::StartFindService(
            [this](score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
                   score::mw::com::FindServiceHandle handle) noexcept {
                OnServiceAvailable(std::move(handles), handle);
            },
            instance.value());
        if (!find_result.has_value()) {
            std::cerr << "Failed to start discovery: " << find_result.error() << std::endl;
            return EXIT_FAILURE;
        }

        std::unique_lock<std::mutex> lock{mutex_};
        if (!completion_cv_.wait_for(lock, kWaitTimeout, [this] { return completed_; })) {
            std::cerr << "Timed out waiting for headlight sample" << std::endl;
            Cleanup();
            return EXIT_FAILURE;
        }
        lock.unlock();
        Cleanup();
        return failed_ ? EXIT_FAILURE : EXIT_SUCCESS;
    }

   private:
    void OnServiceAvailable(
        score::mw::com::ServiceHandleContainer<score::mw::com::HandleType> handles,
        score::mw::com::FindServiceHandle handle) noexcept {
        (void)score::mw::com::GenericProxy::StopFindService(handle);
        if (handles.empty()) {
            Complete(true, "No headlight service handle available");
            return;
        }
        auto proxy_result = score::mw::com::GenericProxy::Create(handles.front());
        if (!proxy_result.has_value()) {
            Complete(true, "Failed to create GenericProxy");
            return;
        }
        proxy_.emplace(std::move(proxy_result).value());
        auto events = proxy_->GetEvents();
        const auto event = events.find(kEventName);
        if (event == events.cend()) {
            Complete(true, "GenericProxy does not expose headlight event");
            return;
        }
        headlight_event_ = &event->second;
        const auto handler = headlight_event_->SetReceiveHandler([this]() noexcept { OnReceive(); });
        if (!handler.has_value()) {
            Complete(true, "Failed to set headlight receive handler");
            return;
        }
        const auto subscription = headlight_event_->Subscribe(kMaxSampleCount);
        if (!subscription.has_value()) {
            Complete(true, "Failed to subscribe to headlight");
            return;
        }
        std::cout << "Subscribed to 'headlight' and waiting for the first sample." << std::endl;
    }

    void OnReceive() noexcept {
        const auto samples = headlight_event_->GetNewSamples(
            [this](score::mw::com::SamplePtr<void> sample) noexcept {
                using PreSerializedData = score::someip_gateway::serializer::PreSerializedData<0>;
                const auto* const data = static_cast<const PreSerializedData*>(sample.Get());
                const bool on = data != nullptr && data->size > 0U && data->data[0] != std::byte{0};
                std::cout << "Received headlight sample: headlights=" << (on ? "on" : "off")
                          << std::endl;
                Complete(false, "");
            },
            kMaxSampleCount);
        if (!samples.has_value()) {
            Complete(true, "Failed to retrieve headlight samples");
        }
    }

    void Complete(bool failure, const char* message) noexcept {
        std::lock_guard<std::mutex> lock{mutex_};
        if (completed_) {
            return;
        }
        failed_ = failure;
        completed_ = true;
        if (failure) {
            std::cerr << message << std::endl;
        }
        completion_cv_.notify_one();
    }

    void Cleanup() noexcept {
        if (headlight_event_ != nullptr) {
            (void)headlight_event_->UnsetReceiveHandler();
            headlight_event_->Unsubscribe();
        }
    }

    std::string configuration_path_;
    std::mutex mutex_;
    std::condition_variable completion_cv_;
    bool completed_{false};
    bool failed_{false};
    std::optional<score::mw::com::GenericProxy> proxy_;
    score::mw::com::GenericProxyEvent* headlight_event_{nullptr};
};

int main(int argc, char* argv[]) {
    std::string configuration_path{std::string{kDefaultConfigurationPath}};
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::string_view{argv[index]} == "--configuration") {
            configuration_path = argv[++index];
        }
    }
    return HeadlightConsumer{std::move(configuration_path)}.Run();
}
