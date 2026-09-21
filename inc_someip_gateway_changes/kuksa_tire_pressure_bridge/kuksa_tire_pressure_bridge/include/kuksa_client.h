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

#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace grpc {
class Channel;
}

namespace score::integration {

class IKuksaClient {
public:
    using FloatCallback = std::function<void(float)>;
    using BoolCallback = std::function<void(bool)>;

    virtual ~IKuksaClient() = default;

    virtual bool Connect() = 0;
    virtual bool PublishBool(std::string_view signal_path, bool value) = 0;
    virtual bool PublishUint16(std::string_view signal_path, std::uint16_t value) = 0;

    // Starts a background streaming subscription for one signal.
    virtual bool SubscribeFloat(std::string signal_path, FloatCallback callback) = 0;
    virtual bool SubscribeBool(std::string signal_path, BoolCallback callback) = 0;

    virtual void Stop() = 0;
};

class KuksaValV1Client final : public IKuksaClient {
public:
    explicit KuksaValV1Client(std::string endpoint);
    ~KuksaValV1Client() override;

    bool Connect() override;
    bool PublishBool(std::string_view signal_path, bool value) override;
    bool PublishUint16(std::string_view signal_path, std::uint16_t value) override;
    bool SubscribeFloat(std::string signal_path, FloatCallback callback) override;
    bool SubscribeBool(std::string signal_path, BoolCallback callback) override;
    void Stop() override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace score::integration
