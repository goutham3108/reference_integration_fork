#pragma once

#include "kuksa_client.h"
#include "tire_pressure_types.h"

#include <functional>
#include <string>

namespace score::integration {

struct TirePressureVssPaths final {
    std::string front_left;
    std::string front_right;
    std::string rear_left;
    std::string rear_right;
};

class TirePressureBridge final {
public:
    using MwComPublishCallback = std::function<void(const TirePressureData&)>;
    using MwComHeadlightPublishCallback = std::function<void(bool)>;

    TirePressureBridge(
        IKuksaClient& kuksa,
        TirePressureVssPaths paths,
        MwComPublishCallback mw_com_publish = {},
        MwComHeadlightPublishCallback mw_com_headlight_publish = {});

    // Call this from the mw::com tire-pressure event receive handler.
    void OnMwComTirePressure(const TirePressureData& data);

    // Call this from the mw::com headlight event receive handler.
    void OnMwComHeadlight(bool is_on);

    // Optional reverse bridge: KUKSA -> mw::com.
    // This subscribes to all four VSS paths and republishes the latest aggregate.
    bool StartKuksaToMwCom();

private:
    void PublishAggregateToMwCom();

    IKuksaClient& kuksa_;
    TirePressureVssPaths paths_;
    MwComPublishCallback mw_com_publish_;
    MwComHeadlightPublishCallback mw_com_headlight_publish_;

    TirePressureData latest_{};
};

}  // namespace score::integration
