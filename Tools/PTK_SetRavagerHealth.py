"""
Protect the King - 2D
Development helper: sets BP_Ravager's MaxHealth.

    UnrealEditor-Cmd.exe <proj> -run=pythonscript ^
        -script="Tools/PTK_SetRavagerHealth.py" -ptkhp=200

Exists so the death path can be exercised without waiting for 7000 HP to drain
one 15-point bite at a time. Always put it back to the balance value afterwards
(Tools/PTK_GenerateSwarmNode.py does that as part of a normal run).
"""

import sys

import unreal

RAVAGER_BP = "/Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager"


def main():
    # A commandlet does not forward unknown switches into sys.argv, so the
    # engine's own command line is the reliable place to read them from.
    value = 7000.0
    tokens = list(sys.argv) + unreal.SystemLibrary.get_command_line().split()
    for arg in tokens:
        if arg.startswith("-ptkhp="):
            value = float(arg.split("=", 1)[1])

    blueprint = unreal.EditorAssetLibrary.load_asset(RAVAGER_BP)
    if blueprint is None:
        unreal.log_error("[PTK] BP_Ravager not found")
        return

    cdo = unreal.get_default_object(blueprint.generated_class())
    health = cdo.get_editor_property("health_component")
    if health is None:
        unreal.log_error("[PTK] BP_Ravager has no health component")
        return

    health.set_editor_property("max_health", value)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    unreal.log("[PTK] BP_Ravager MaxHealth = {0}".format(value))


main()
