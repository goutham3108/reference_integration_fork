#pragma once

namespace score::integration {

struct TirePressureData final {
    float front_left_bar{};
    float front_right_bar{};
    float rear_left_bar{};
    float rear_right_bar{};
};

}  // namespace score::integration
