// This file is a copy of inc_someip_gateway/tests/integration/vehicle_high_beam_remote_app/main.cpp
// It is packaged here so the demo is self-contained under sdv-hack-demo.

#include <algorithm>
#include <atomic>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <iostream>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>
#include <vsomeip/vsomeip.hpp>

#include <kvsbuilder.hpp>
#include "high_beam_udp_protocol.h"
#include "sdv-hack-demo/include/speed_payload.h"
#include "score/mw/lifecycle/report_running.h"
#include "score/mw/log/logging.h"

namespace {

constexpr auto kPublishPeriod = std::chrono::seconds{2};
constexpr char kSensorStateKey[] = "high_beam_state";
constexpr std::uint16_t kDefaultBridgePort = 35000U;
constexpr std::uint16_t kDefaultRemotePort = 35001U;

struct Route {
    std::string name;
    std::uint16_t service;
    std::uint16_t vehicle_instance;
    std::uint16_t remote_instance;
    std::uint16_t vehicle_event;
    std::uint16_t remote_event;
};

std::optional<bool> ParseBooleanInput(const std::string& input) {
    if (input == "true") {
        return true;
    }
    if (input == "false") {
        return false;
    }
    return std::nullopt;
}

std::optional<double> ParseSpeedInput(const std::string& input) {
    try {
        std::size_t parsed = 0U;
        const double value = std::stod(input, &parsed);
        if (parsed != input.size()) {
            return std::nullopt;
        }
        return value;
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

void PrintRemoteMenu() {
    std::cout << "\nRemote menu\n"
              << "1  High-beam (true/false)\n"
              << "2  Vehicle.speed (number)\n"
              << "q  Quit input\n"
              << "Select: " << std::flush;
}

std::uint16_t ResolvePort(const char* name, const std::uint16_t fallback) {
    const char* value = std::getenv(name);
    return value == nullptr ? fallback : static_cast<std::uint16_t>(std::stoi(value));
}

std::string ResolveAddress(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return value == nullptr || value[0] == '\0' ? fallback : value;
}

bool SetAddress(sockaddr_in& address, const std::string& value) {
    return inet_pton(AF_INET, value.c_str(), &address.sin_addr) == 1;
}

std::optional<std::vector<Route>> LoadRoutes() {
    const char* const configured = std::getenv("SIGNAL_ROUTE_CONFIG");
    const std::string path = configured == nullptr || configured[0] == '\0' ? "signal_routes.json" : configured;
    std::ifstream input{path};
    if (!input.is_open()) {
        score::mw::log::LogError() << "Cannot open signal route configuration";
        return std::nullopt;
    }
    try {
        const auto document = nlohmann::json::parse(input);
        std::vector<Route> routes;
        for (const auto& item : document.at("routes")) {
            routes.push_back(Route{item.at("name").get<std::string>(), item.at("service").get<std::uint16_t>(),
                                   item.at("vehicleInstance").get<std::uint16_t>(),
                                   item.at("remoteInstance").get<std::uint16_t>(),
                                   item.at("vehicleEvent").get<std::uint16_t>(),
                                   item.at("remoteEvent").get<std::uint16_t>()});
        }
        return routes;
    } catch (const std::exception& error) {
        score::mw::log::LogError() << "Invalid signal route configuration: " << error.what();
        return std::nullopt;
    }
}

int CreateUdpSocket(const std::uint16_t port, const std::string& bind_ip) {
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (socket_fd < 0) {
        return -1;
    }
    sockaddr_in address{};
    address.sin_family = AF_INET;
    if (!SetAddress(address, bind_ip)) {
        close(socket_fd);
        return -1;
    }
    address.sin_port = htons(port);
    if (bind(socket_fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0) {
        close(socket_fd);
        return -1;
    }
    return socket_fd;
}

}  // namespace

int main() {
    const auto routes = LoadRoutes();
    if (!routes.has_value() || routes->empty()) {
        return 1;
    }
    const auto high_beam = std::find_if(routes->begin(), routes->end(), [](const Route& route) {
        return route.name == "high_beam";
    });
    if (high_beam == routes->end()) {
        score::mw::log::LogError() << "Route configuration has no high_beam route";
        return 1;
    }
    const char* const configured_kvs_dir = std::getenv("HIGH_BEAM_KVS_DIR");
    const std::string kvs_dir = configured_kvs_dir != nullptr && configured_kvs_dir[0] != '\0'
                                    ? configured_kvs_dir
                                    : "/tmp/score_high_beam_sensor";
    std::error_code filesystem_error;
    std::filesystem::create_directories(kvs_dir, filesystem_error);
    if (filesystem_error) {
        score::mw::log::LogError() << "Cannot create sensor KVS directory: " << kvs_dir;
        return 1;
    }
    score::mw::per::kvs::KvsBuilder kvs_builder{score::mw::per::kvs::InstanceId{1U}};
    kvs_builder.dir(std::string{kvs_dir});
    auto kvs_result = kvs_builder.build();
    if (!kvs_result.has_value()) {
        score::mw::log::LogError() << "Cannot open sensor KVS in " << kvs_dir;
        return 1;
    }
    auto sensor_store = std::make_shared<score::mw::per::kvs::Kvs>(std::move(kvs_result).value());
    std::atomic<bool> sensor_state{false};

    const std::uint16_t bridge_port = ResolvePort("HIGH_BEAM_BRIDGE_UDP_PORT", kDefaultBridgePort);
    const std::uint16_t remote_port = ResolvePort("HIGH_BEAM_REMOTE_UDP_PORT", kDefaultRemotePort);
    const std::string bind_ip = ResolveAddress("HIGH_BEAM_BIND_IP", "0.0.0.0");
    const std::string bridge_ip = ResolveAddress("HIGH_BEAM_BRIDGE_IP", "127.0.0.1");
    const int udp_socket = CreateUdpSocket(remote_port, bind_ip);
    if (udp_socket < 0) {
        score::mw::log::LogError() << "Failed to bind remote UDP port " << remote_port;
        return 1;
    }
    sockaddr_in bridge_address{};
    bridge_address.sin_family = AF_INET;
    if (!SetAddress(bridge_address, bridge_ip)) {
        score::mw::log::LogError() << "Invalid HIGH_BEAM_BRIDGE_IP: " << bridge_ip;
        close(udp_socket);
        return 1;
    }
    bridge_address.sin_port = htons(bridge_port);
    if (std::getenv("PROCESSIDENTIFIER") != nullptr) {
        score::mw::lifecycle::report_running();
    }

    std::thread input_thread([&sensor_state, &sensor_store, &routes, &bridge_address, udp_socket]() {
        std::ifstream terminal_input{"/dev/tty"};
        std::istream& input_stream = terminal_input.is_open() ? static_cast<std::istream&>(terminal_input)
                                                               : std::cin;
        PrintRemoteMenu();
        std::string input;
        while (std::getline(input_stream, input)) {
            if (input == "q") {
                break;
            }
            if (input == "1") {
                std::cout << "High-beam value (true/false): " << std::flush;
                if (!std::getline(input_stream, input)) {
                    break;
                }
                const auto value = ParseBooleanInput(input);
                if (!value.has_value()) {
                    score::mw::log::LogWarn() << "Invalid high-beam input. Enter true or false.";
                    continue;
                }
                sensor_state.store(value.value());
                (void)sensor_store->set_value(kSensorStateKey, score::mw::per::kvs::KvsValue{value.value()});
                (void)sensor_store->flush();
                score::mw::log::LogWarn() << "Remote input set High.IsOn="
                                          << (value.value() ? "true" : "false");
                PrintRemoteMenu();
                continue;
            }
            if (input == "2") {
                const auto dynamics = std::find_if(routes->begin(), routes->end(), [](const Route& route) {
                    return route.name == "vehicle_dynamics";
                });
                if (dynamics == routes->end()) {
                    score::mw::log::LogError() << "Route configuration has no vehicle_dynamics route";
                    continue;
                }
                std::cout << "Vehicle.speed value: " << std::flush;
                if (!std::getline(input_stream, input)) {
                    break;
                }
                const auto speed = ParseSpeedInput(input);
                if (!speed.has_value()) {
                    score::mw::log::LogWarn() << "Invalid speed input. Enter a number.";
                    continue;
                }
                high_beam_udp::Frame frame{dynamics->service, dynamics->remote_instance,
                                           dynamics->remote_event, 9U, {}};
                vehicle_dynamics_wire::EncodeSpeed(speed.value(), 3U, frame.payload.data());
                const auto encoded = high_beam_udp::Encode(frame);
                (void)sendto(udp_socket, encoded.data(), encoded.size(), 0,
                             reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
                score::mw::log::LogWarn() << "Remote published Vehicle.speed=" << speed.value();
                PrintRemoteMenu();
                continue;
            }
            score::mw::log::LogWarn() << "Invalid menu option. Select 1, 2, or q.";
        }
    });
    input_thread.detach();

    std::thread receive_thread([udp_socket, &sensor_state, &sensor_store, &routes, &bridge_address]() {
        std::array<std::uint8_t, high_beam_udp::kFrameSize> bytes{};
        while (true) {
            sockaddr_in sender{};
            socklen_t sender_size = sizeof(sender);
            const auto received = recvfrom(udp_socket, bytes.data(), bytes.size(), 0,
                                           reinterpret_cast<sockaddr*>(&sender), &sender_size);
            if (received <= 0) {
                continue;
            }
            const auto frame = high_beam_udp::Decode(bytes.data(), static_cast<std::size_t>(received));
            const auto route = frame.has_value()
                                   ? std::find_if(routes->begin(), routes->end(), [&frame](const Route& candidate) {
                                         return frame->service == candidate.service &&
                                                frame->instance == candidate.vehicle_instance &&
                                                frame->event == candidate.vehicle_event;
                                     })
                                   : routes->end();
            if (!frame.has_value() || route == routes->end()) {
                score::mw::log::LogError() << "Remote app received invalid UDP SOME/IP frame";
                continue;
            }
            char sender_ip[INET_ADDRSTRLEN]{};
            const char* const sender_address =
                inet_ntop(AF_INET, &sender.sin_addr, sender_ip, sizeof(sender_ip));
            if (route->name != "high_beam") {
                if (frame->payload_size == sizeof(double) + 1U) {
                    const double received_value = vehicle_dynamics_wire::DecodeSpeed(frame->payload.data());
                    score::mw::log::LogWarn() << "Remote received Vehicle.speed=" << received_value
                                              << " from "
                                              << (sender_address == nullptr ? "<unknown>" : sender_address)
                                              << ":" << ntohs(sender.sin_port);
                } else {
                    score::mw::log::LogWarn() << "Remote received " << route->name
                                              << " payload_size=" << frame->payload_size;
                }
                high_beam_udp::Frame acknowledgement{route->service, route->remote_instance,
                                                      route->remote_event, frame->payload_size, frame->payload};
                const auto encoded = high_beam_udp::Encode(acknowledgement);
                (void)sendto(udp_socket, encoded.data(), encoded.size(), 0,
                             reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
                if (frame->payload_size == sizeof(double) + 1U) {
                    const double acked_value = vehicle_dynamics_wire::DecodeSpeed(frame->payload.data());
                    score::mw::log::LogWarn() << "Remote forwarded Vehicle.speed=" << acked_value;
                } else {
                    score::mw::log::LogWarn() << "Remote acknowledged " << route->name
                                              << " payload_size=" << frame->payload_size;
                }
                continue;
            }
            auto payload = vsomeip::runtime::get()->create_payload();
            payload->set_data(std::vector<vsomeip::byte_t>(frame->payload.begin(),
                                                           frame->payload.begin() + frame->payload_size));
            const bool value = payload->get_data()[0] == 1U;
            sensor_state.store(value);
            (void)sensor_store->set_value(kSensorStateKey, score::mw::per::kvs::KvsValue{value});
            (void)sensor_store->flush();
            score::mw::log::LogWarn() << "Remote app converted UDP to SOME/IP High.IsOn="
                                      << (value ? "true" : "false");
        }
    });

    while (true) {
        const bool value = sensor_state.load();
        high_beam_udp::Frame outbound{high_beam->service, high_beam->remote_instance,
                          high_beam->remote_event, 1U,
                          {static_cast<std::uint8_t>(value)}};
        const auto frame = high_beam_udp::Encode(outbound);
        (void)sendto(udp_socket, frame.data(), frame.size(), 0,
                     reinterpret_cast<const sockaddr*>(&bridge_address), sizeof(bridge_address));
        std::this_thread::sleep_for(kPublishPeriod);
    }
    receive_thread.join();
    close(udp_socket);
    return 0;
}
