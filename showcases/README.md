# Logging App Demo
 
This Logging App demonstrates logging using mw::log with all log levels and configured backends (kConsole|kRemote|kFile) enabled.

For remote (DLT) logging, please refer to the following documentation:
 
[Remote logging](https://github.com/eclipse-score/logging/blob/main/score/datarouter/doc/guideline/dlt_capture_demo.md)

## Vehicle High-Beam SOME/IP Demo

The [vehicle high-beam demo](../sdv-hack-demo/README.md) bridges
`Vehicle.Body.Lights.Beam.High.IsOn` through `gatewayd`, `someipd`, a SOME/IP
to TCP network bridge, and a remote TCP application. The editable end-to-end
flow is documented in [the Draw.io diagram](../sdv-hack-demo/architecture.drawio).