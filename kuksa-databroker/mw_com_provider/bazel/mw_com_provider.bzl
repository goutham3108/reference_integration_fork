def mw_com_provider_cargo_commands(
        check_name = "cargo_check_mw_com_provider",
        test_name = "cargo_test_mw_com_provider",
        live_e2e_name = "score_lola_live_e2e",
        visibility = None):
    native.sh_binary(
        name = check_name,
        srcs = ["bazel/cargo_provider.sh"],
        args = ["check"],
        visibility = visibility,
    )

    native.sh_binary(
        name = test_name,
        srcs = ["bazel/cargo_provider.sh"],
        args = ["test"],
        visibility = visibility,
    )

    native.sh_binary(
        name = live_e2e_name,
        srcs = ["bazel/cargo_provider.sh"],
        args = ["score-lola-live-e2e-local"],
        data = [
            "scripts/run-score-lola-live-e2e-local.sh",
            ":provider_generated_artifacts",
            "@score_communication//score/mw/com/example/vehicle-dynamics-example:vehicle-dynamics-example",
        ],
        visibility = visibility,
    )

def mw_com_provider_score_lola_runtime_files(name, srcs, visibility = None):
    native.filegroup(
        name = name,
        srcs = srcs,
        visibility = visibility,
    )