#ifndef SDV_HACK_DEMO_SIGNAL_TEST_VALUES_H
#define SDV_HACK_DEMO_SIGNAL_TEST_VALUES_H

#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

namespace body_signal_test {

struct Signal {
    std::string api_name;
    std::string event_name;
    std::string datatype;
};

using Payload = std::vector<std::uint8_t>;

inline std::vector<Signal> LoadSignals(const nlohmann::json& document) {
    std::vector<Signal> signals;
    for (const auto& route : document.at("routes")) {
        if (route.at("service").get<std::uint16_t>() != 17152U) {
            continue;
        }
        Signal signal{route.at("apiName").get<std::string>(),
                      route.at("eventName").get<std::string>(),
                      route.at("datatype").get<std::string>()};
        if (signal.datatype != "boolean" && signal.datatype != "uint8" && signal.datatype != "string") {
            throw std::runtime_error("Unsupported datatype for " + signal.api_name);
        }
        for (const auto& previous : signals) {
            if (previous.event_name == signal.event_name || previous.api_name == signal.api_name) {
                throw std::runtime_error("Duplicate body signal: " + signal.api_name);
            }
        }
        signals.push_back(std::move(signal));
    }
    if (signals.empty()) {
        throw std::runtime_error("No body signals in route configuration");
    }
    return signals;
}

inline std::vector<Payload> TestValues(const Signal& signal) {
    if (signal.datatype == "boolean") {
        return {{0U}, {1U}, {0U}};
    }
    if (signal.datatype == "uint8") {
        return {{0U}, {50U}, {100U}, {0U}};
    }
    if (signal.datatype == "string") {
        return {{'O', 'F', 'F'}, {'F', 'A', 'S', 'T'}, {'O', 'F', 'F'}};
    }
    throw std::runtime_error("Unsupported datatype for " + signal.api_name);
}

inline std::string DisplayValue(const Signal& signal, const Payload& payload) {
    if (signal.datatype == "boolean" && payload.size() == 1U && payload[0] <= 1U) {
        return payload[0] == 0U ? "false" : "true";
    }
    if (signal.datatype == "uint8" && payload.size() == 1U) {
        return std::to_string(payload[0]);
    }
    if (signal.datatype == "string" && payload.size() <= 32U) {
        return std::string{payload.begin(), payload.end()};
    }
    return "<invalid payload>";
}

}

#endif