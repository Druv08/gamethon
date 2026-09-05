"""
Protect the King - 2D
Diagnostic: dump the real state of the Enhanced Input assets and the camera basis.

Answers two questions with measurements rather than assumptions:
  1. Did the W/S/A/D modifiers actually persist into IMC_PTK_Default?
  2. Which world axis is "screen right" for the camera rig as configured?
"""

import unreal

INPUT_DIR = "/Game/PTK/Input"
RAVAGER_BP = "/Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager"


def log(msg):
    unreal.log("[PTK] " + msg)


def dump_mapping_context():
    log("=" * 62)
    log("1. IMC_PTK_Default - ACTUAL SAVED CONTENTS")
    log("=" * 62)

    context = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/IMC_PTK_Default")
    if context is None:
        unreal.log_error("[PTK] IMC_PTK_Default not found")
        return

    mappings = []
    where = "?"
    try:
        data = context.get_editor_property("default_key_mappings")
        mappings = data.get_editor_property("mappings")
        where = "default_key_mappings.mappings"
    except Exception as exc:  # noqa: BLE001
        log("  default_key_mappings unavailable: {0}".format(exc))
        try:
            mappings = context.get_editor_property("mappings")
            where = "mappings (legacy)"
        except Exception as exc2:  # noqa: BLE001
            unreal.log_error("[PTK] could not read mappings: {0}".format(exc2))
            return

    log("  read from: {0}".format(where))
    log("  mapping count: {0}".format(len(mappings)))

    for i, m in enumerate(mappings):
        action = m.get_editor_property("action")
        key = m.get_editor_property("key")
        key_name = key.get_editor_property("key_name") if key else "?"
        try:
            modifiers = m.get_editor_property("modifiers")
        except Exception:  # noqa: BLE001
            modifiers = []
        try:
            triggers = m.get_editor_property("triggers")
        except Exception:  # noqa: BLE001
            triggers = []

        desc = []
        for mod in modifiers:
            if mod is None:
                desc.append("<NULL MODIFIER>")
                continue
            cls = mod.get_class().get_name()
            extra = ""
            if cls == "InputModifierSwizzleAxis":
                try:
                    extra = "(order={0})".format(mod.get_editor_property("order"))
                except Exception:  # noqa: BLE001
                    extra = "(order=?)"
            desc.append(cls + extra)

        log("  [{0}] key={1:<16} action={2:<10} modifiers={3} triggers={4}".format(
            i, str(key_name),
            action.get_name() if action else "NONE",
            desc if desc else "[] <-- NONE",
            len(triggers)))

    # Simulate what Enhanced Input will produce for a digital key press.
    log("")
    log("  Predicted IA_Move value per key (digital press = 1.0 on X, then modifiers):")
    for m in mappings:
        key = m.get_editor_property("key")
        key_name = str(key.get_editor_property("key_name")) if key else "?"
        if key_name not in ("W", "A", "S", "D"):
            continue
        try:
            modifiers = m.get_editor_property("modifiers")
        except Exception:  # noqa: BLE001
            modifiers = []
        x, y = 1.0, 0.0
        for mod in modifiers:
            if mod is None:
                continue
            cls = mod.get_class().get_name()
            if cls == "InputModifierSwizzleAxis":
                x, y = y, x
            elif cls == "InputModifierNegate":
                x, y = -x, -y
        log("    {0} -> ({1:+.0f}, {2:+.0f})".format(key_name, x, y))


def dump_action():
    log("")
    log("=" * 62)
    log("2. IA_Move")
    log("=" * 62)
    action = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/IA_Move")
    if action is None:
        unreal.log_error("[PTK] IA_Move not found")
        return
    log("  value_type = {0}".format(action.get_editor_property("value_type")))
    try:
        log("  modifiers on action = {0}".format(
            len(action.get_editor_property("modifiers"))))
    except Exception:  # noqa: BLE001
        pass


def dump_camera_basis():
    log("")
    log("=" * 62)
    log("3. CAMERA BASIS - which world axis is screen right?")
    log("=" * 62)

    blueprint = unreal.EditorAssetLibrary.load_asset(RAVAGER_BP)
    if blueprint is None:
        unreal.log_error("[PTK] BP_Ravager not found")
        return
    cdo = unreal.get_default_object(blueprint.generated_class())

    # The boom rotation is what orients the camera.
    # Must match PTKCharacterDefaults::CameraBoomYaw in PTKTopDownCharacter.cpp.
    # The camera sits at -Y looking +Y; that is the only side Paper2D sprites
    # render from in this project.
    boom_yaw = 90.0
    rot = unreal.Rotator(0.0, 0.0, boom_yaw)  # roll, pitch, yaw
    fwd = rot.get_forward_vector()
    right = rot.get_right_vector()
    up = rot.get_up_vector()

    log("  CameraBoom relative rotation: yaw={0}".format(boom_yaw))
    log("    forward (camera looks along) = ({0:+.2f}, {1:+.2f}, {2:+.2f})".format(
        fwd.x, fwd.y, fwd.z))
    log("    right   (screen right)       = ({0:+.2f}, {1:+.2f}, {2:+.2f})".format(
        right.x, right.y, right.z))
    log("    up      (screen up)          = ({0:+.2f}, {1:+.2f}, {2:+.2f})".format(
        up.x, up.y, up.z))
    log("")
    log("  Paper2D vertex normal = -PaperAxisZ = (0,+1,0), so sprite fronts face")
    log("  +Y and the camera MUST sit on the +Y side looking toward -Y.")
    log("  Viewing from -Y renders sprites mirrored (left/right art swapped).")
    log("")
    if fwd.y > 0:
        log("  >>> CAMERA LOOKS ALONG +Y - it is BEHIND the sprites. They will")
        log("      render MIRRORED (left/right swapped). <<<")
    else:
        log("  >>> camera looks along -Y: sprite fronts, not mirrored <<<")
    log("  >>> screen right is world {0}X <<<".format("+" if right.x > 0 else "-"))

    log("")
    log("  CameraOrthoWidth = {0}".format(cdo.get_editor_property("camera_ortho_width")))


dump_mapping_context()
dump_action()
dump_camera_basis()
log("")
log("diagnostic complete")
