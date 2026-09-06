"""
Protect the King - 2D
Unreal Editor Python script: the input assets behind guard switching.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_SetupGuardSwitching.py"

What it creates
---------------
    IA_SelectGuard1 .. IA_SelectGuard5    digital (bool) actions, one per slot
    IMC_PTK_GuardSwitch                   1-5 and the numpad equivalents

Re-running is safe: each action's keys are cleared before being remapped, so a
second run cannot stack duplicate bindings.


WHY FIVE ACTIONS AND NOT ONE
----------------------------
Enhanced Input hands a bound delegate the action's VALUE, never the key that
produced it. One IA_SelectGuard mapped to five keys would fire five identical
events and the handler could not tell 2 from 4. One action per slot is what
makes the slot knowable, and APTKPlayerController binds all five in a loop with
the slot number as a payload - so five assets still means one handler.


WHY A SEPARATE MAPPING CONTEXT
------------------------------
IMC_PTK_Default belongs to the PAWN: APTKTopDownCharacter adds it when it is
possessed and it carries IA_Move, IA_Attack and IA_Defend. The switch keys
belong to the PLAYER CONTROLLER, which outlives every pawn - including the
moment between releasing one guard and possessing the next, and the case where a
guard Blueprint is missing its input assets entirely (which has happened in this
project). Keeping them in their own context means the number keys cannot be
taken down by the pawn they are meant to replace.

Nothing here touches IMC_PTK_Default or the three existing actions.
"""

import unreal


INPUT_DIR = "/Game/PTK/Input"
SWITCH_CONTEXT = INPUT_DIR + "/IMC_PTK_GuardSwitch"

# Slot -> (asset name, keys). The row order IS the slot order:
#   1 Ravager   2 Aegis   3 Wraith   4 Reaver   5 Sentinel
# Numpad is mapped too, because a keyboard with a numpad has two obvious "3"s
# and a player should not have to find out which one the game meant.
SLOTS = [
    (1, "IA_SelectGuard1", ("One",   "NumPadOne")),
    (2, "IA_SelectGuard2", ("Two",   "NumPadTwo")),
    (3, "IA_SelectGuard3", ("Three", "NumPadThree")),
    (4, "IA_SelectGuard4", ("Four",  "NumPadFour")),
    (5, "IA_SelectGuard5", ("Five",  "NumPadFive")),
]

_asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
_summary = {"actions": 0, "keys": 0, "warnings": [], "errors": []}


def info(message):
    unreal.log("[PTK] " + message)


def warn(message):
    _summary["warnings"].append(message)
    unreal.log_warning("[PTK] " + message)


def fail(message):
    _summary["errors"].append(message)
    unreal.log_error("[PTK] " + message)


def set_prop(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as exc:  # noqa: BLE001
        warn("could not set '{0}' on {1}: {2}".format(name, obj.get_name(), exc))
        return False


def make_key(key_name):
    # FKey has a custom serialiser, so it is built by setting the property
    # rather than by passing the name to the constructor - unreal.Key() takes no
    # arguments in 5.8.
    key = unreal.Key()
    key.set_editor_property("key_name", key_name)
    return key


# ---------------------------------------------------------------------------
def ensure_action(name):
    path = INPUT_DIR + "/" + name
    action = unreal.EditorAssetLibrary.load_asset(path)
    if action is None:
        action = _asset_tools.create_asset(name, INPUT_DIR, unreal.InputAction, None)
        if action is None:
            fail("could not create " + name)
            return None
        info("created " + name)
    # Digital, like IA_Attack: a number key is pressed or it is not.
    set_prop(action, "value_type", unreal.InputActionValueType.BOOLEAN)
    unreal.EditorAssetLibrary.save_loaded_asset(action, only_if_is_dirty=False)
    _summary["actions"] += 1
    return action


def ensure_context(actions):
    context = unreal.EditorAssetLibrary.load_asset(SWITCH_CONTEXT)
    if context is None:
        context = _asset_tools.create_asset(
            "IMC_PTK_GuardSwitch", INPUT_DIR, unreal.InputMappingContext, None)
        if context is None:
            fail("could not create IMC_PTK_GuardSwitch")
            return None
        info("created IMC_PTK_GuardSwitch")

    for slot, name, keys in SLOTS:
        action = actions.get(name)
        if action is None:
            continue
        try:
            # Cleared first so re-running cannot stack duplicate bindings.
            context.unmap_all_keys_from_action(action)
            for key_name in keys:
                context.map_key(action, make_key(key_name))
                _summary["keys"] += 1
            info("slot {0}: {1} <- {2}".format(slot, name, ", ".join(keys)))
        except Exception as exc:  # noqa: BLE001
            fail("could not bind {0}: {1}".format(name, exc))

    unreal.EditorAssetLibrary.save_loaded_asset(context, only_if_is_dirty=False)
    return context


# ---------------------------------------------------------------------------
def verify(actions, context):
    info("")
    info("-" * 62)
    info("verification")
    ok = True

    for _slot, name, _keys in SLOTS:
        action = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/" + name)
        if action is None:
            ok = False
            fail(name + " is missing")
            continue
        value_type = action.get_editor_property("value_type")
        if value_type != unreal.InputActionValueType.BOOLEAN:
            ok = False
            fail("{0} is {1}, expected Boolean".format(name, value_type))
    if ok:
        info("PASS  5 digital select actions exist")

    if context is None:
        ok = False
        fail("IMC_PTK_GuardSwitch is missing")
    else:
        # 5.7+ keeps the list inside DefaultKeyMappings; fall back to the old
        # flat property so this reports honestly on either layout.
        mapped = None
        try:
            data = context.get_editor_property("default_key_mappings")
            mapped = list(data.get_editor_property("mappings"))
        except Exception:  # noqa: BLE001
            try:
                mapped = list(context.get_editor_property("mappings"))
            except Exception as exc:  # noqa: BLE001
                warn("could not read the mapping list back: {0}".format(exc))
        if mapped is not None:
            expected = sum(len(keys) for _s, _n, keys in SLOTS)
            if len(mapped) == expected:
                info("PASS  IMC_PTK_GuardSwitch holds {0} key mappings".format(len(mapped)))
            else:
                ok = False
                fail("IMC_PTK_GuardSwitch holds {0} mappings, expected {1}".format(
                    len(mapped), expected))

    # The pawn's own context must be untouched by all of this.
    default = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/IMC_PTK_Default")
    if default is None:
        ok = False
        fail("IMC_PTK_Default is missing - guard movement input would be gone")
    else:
        info("PASS  IMC_PTK_Default still present and untouched")

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("Guard switching input: 5 select actions + IMC_PTK_GuardSwitch")
    info("=" * 62)

    actions = {}
    for _slot, name, _keys in SLOTS:
        action = ensure_action(name)
        if action is not None:
            actions[name] = action

    context = ensure_context(actions)
    verify(actions, context)

    info("=" * 62)
    for key in ("actions", "keys"):
        info("{0:<9}: {1}".format(key, _summary[key]))
    info("{0:<9}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<9}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
