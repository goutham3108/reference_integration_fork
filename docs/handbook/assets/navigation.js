(() => {
  const descriptions = {
    "Start": "Map, purpose, architecture, and repository orientation",
    "Workspace": "Selects dependencies, toolchains, and build targets",
    "Signals": "Keeps routes, manifests, and generated bindings aligned",
    "Vehicle Apps": "Issues commands and checks returned signal values",
    "Gateway": "Connects shared-memory services to SOME/IP events",
    "Serializer": "Adapts service names to the gateway serializer",
    "UDP Bridge": "Carries configured SOME/IP payloads over demo UDP",
    "Remote App": "Applies high-beam state and returns signal feedback",
    "S-CORE": "Provides common libraries and shared-memory middleware",
    "KUKSA": "Exposes vehicle signals through gRPC and middleware",
    "SDV Runtime": "Connects the optional container syncer to the broker",
    "Platforms": "Packages and launches platform integration examples",
    "Engineering": "Build, configuration, tests, changes, and debugging"
  };
  const annotate = () => {
    document.querySelectorAll(".md-tabs__link").forEach((link) => {
      const description = descriptions[link.textContent.trim()];
      if (description) {
        link.title = description;
        link.setAttribute("aria-label", `${link.textContent.trim()}: ${description}`);
      }
    });
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", annotate);
  } else {
    annotate();
  }
})();
