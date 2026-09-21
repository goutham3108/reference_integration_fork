# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************


def test_tire_pressure_consumer_receives_sample(tire_pressure_consumer_output):
    assert "Subscribed to 'tire_pressure'" in tire_pressure_consumer_output
    assert "Received tire_pressure sample #1" in tire_pressure_consumer_output
