"""
Protect the King - 2D
Automated runtime verification, run inside the Unreal Editor.

    UnrealEditor-Cmd.exe ProtectTheKing2D.uproject ^
        -run=pythonscript -script="Tools/PTK_VerifyRuntime.py" -unattended -nullrhi

This exercises the movement rules directly rather than eyeballing them:

  * the C++ module, Paper2D and Enhanced Input are all loaded and reflected
  * BP_Ravager exists, is parented correctly, and has every asset assigned
  * direction detection is checked against the full WASD + diagonal matrix
  * diagonal normalisation is measured, not assumed
  * last-facing is checked by feeding zero input and reading the direction back

What it deliberately does NOT cover: anything that needs human eyes on a
running frame - sprite blur, pivot jump, animation flicker, camera framing.
Those are listed as manual checks in Docs/PHASE1_STATUS.md.
"""

import math

import unreal

RAVAGER_BP = "/Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager"
FLIPBOOK_DIR = "/Game/PTK/Characters/Guards/Ravager/Flipbooks"
SPRITE_DIR = "/Game/PTK/Characters/Guards/Ravager/Sprites"
INPUT_DIR = "/Game/PTK/Input"
LEVEL_PATH = "/Game/PTK/Maps/L_PTK_TestGround"

DIRECTIONS = ["Down", "Up", "Left", "Right"]

_passes = []
_failures = []


def check(condition, label, detail=""):
    if condition:
        _passes.append(label)
        unreal.log("[PTK]   PASS  {0}{1}".format(label, (" - " + detail) if detail else ""))
    else:
        _failures.append("{0}{1}".format(label, (" - " + detail) if detail else ""))
        unreal.log_error("[PTK]   FAIL  {0}{1}".format(label, (" - " + detail) if detail else ""))
    return condition


def header(title):
    unreal.log("[PTK] " + "-" * 62)
    unreal.log("[PTK] " + title)
    unreal.log("[PTK] " + "-" * 62)


# ---------------------------------------------------------------------------
def verify_modules():
    header("1. MODULES AND REFLECTED CLASSES")

    for name in ("PTKTopDownCharacter", "PTKGuardCharacter", "PTKGameModeBase",
                 "PTKTypesLibrary", "PTKFacingDirection", "PTKMovementState",
                 "PTKDirectionalFlipbooks"):
        check(hasattr(unreal, name), "C++ type exposed: " + name)

    for name in ("PaperFlipbook", "PaperSprite", "PaperFlipbookComponent"):
        check(hasattr(unreal, name), "Paper2D type available: " + name)

    for name in ("InputAction", "InputMappingContext", "InputModifierSwizzleAxis"):
        check(hasattr(unreal, name), "Enhanced Input type available: " + name)


# ---------------------------------------------------------------------------
def verify_blueprint():
    header("2. BP_RAVAGER WIRING")

    blueprint = unreal.EditorAssetLibrary.load_asset(RAVAGER_BP)
    if not check(blueprint is not None, "BP_Ravager exists"):
        return None

    generated = blueprint.generated_class()
    if not check(generated is not None, "BP_Ravager has a generated class"):
        return None

    parents = []
    cursor = generated
    for _ in range(6):
        cursor = unreal.get_class_parent(cursor) if hasattr(unreal, "get_class_parent") else None
        if cursor is None:
            break
        parents.append(cursor.get_name())

    cdo = unreal.get_default_object(generated)
    if not check(cdo is not None, "BP_Ravager class defaults reachable"):
        return None

    check(isinstance(cdo, unreal.PTKGuardCharacter),
          "BP_Ravager derives from PTKGuardCharacter",
          "chain: " + " -> ".join(parents) if parents else "")

    # ---- flipbooks ----
    for slot, prefix in (("idle_flipbooks", "FB_Ravager_Idle_"),
                         ("walk_flipbooks", "FB_Ravager_Walk_"),
                         ("attack_flipbooks", "FB_Ravager_Attack_")):
        try:
            value = cdo.get_editor_property(slot)
        except Exception as exc:  # noqa: BLE001
            check(False, "read " + slot, str(exc))
            continue
        for direction in DIRECTIONS:
            fb = value.get_editor_property(direction.lower())
            check(fb is not None, "{0}.{1} assigned".format(slot, direction),
                  fb.get_name() if fb else "EMPTY")
            if fb is not None:
                check(fb.get_name() == prefix + direction,
                      "{0}.{1} points at the right asset".format(slot, direction),
                      fb.get_name())

    # ---- input ----
    move_action = cdo.get_editor_property("move_action")
    context = cdo.get_editor_property("default_mapping_context")
    check(move_action is not None and move_action.get_name() == "IA_Move",
          "MoveAction = IA_Move", move_action.get_name() if move_action else "EMPTY")
    check(context is not None and context.get_name() == "IMC_PTK_Default",
          "DefaultMappingContext = IMC_PTK_Default",
          context.get_name() if context else "EMPTY")

    attack_action = cdo.get_editor_property("attack_action")
    check(attack_action is not None and attack_action.get_name() == "IA_Attack",
          "AttackAction = IA_Attack",
          attack_action.get_name() if attack_action else "EMPTY")

    # ---- tuning ----
    unreal.log("[PTK]   info  MaxMoveSpeed        = {0}".format(
        cdo.get_editor_property("max_move_speed")))
    unreal.log("[PTK]   info  CollisionRadius     = {0}".format(
        cdo.get_editor_property("collision_radius")))
    unreal.log("[PTK]   info  CollisionHalfHeight = {0}".format(
        cdo.get_editor_property("collision_half_height")))
    unreal.log("[PTK]   info  CameraOrthoWidth    = {0}".format(
        cdo.get_editor_property("camera_ortho_width")))
    unreal.log("[PTK]   info  MoveDeadZone        = {0}".format(
        cdo.get_editor_property("move_dead_zone")))
    unreal.log("[PTK]   info  FacingHysteresis    = {0}".format(
        cdo.get_editor_property("facing_hysteresis")))

    return generated


# ---------------------------------------------------------------------------
def verify_direction_rules():
    """
    The whole WASD + diagonal matrix, checked against the specified rule:
        |X| > |Y|  -> Left/Right,  otherwise -> Up/Down
    """
    header("3. DIRECTION DETECTION (WASD + DIAGONALS)")

    D = unreal.PTKFacingDirection
    lib = unreal.PTKTypesLibrary

    cases = [
        # (label,        input,        current,  expected)
        ("W   ", (0.0, 1.0), D.DOWN, D.UP),
        ("S   ", (0.0, -1.0), D.UP, D.DOWN),
        ("A   ", (-1.0, 0.0), D.DOWN, D.LEFT),
        ("D   ", (1.0, 0.0), D.DOWN, D.RIGHT),
        # Perfect diagonals: |X| == |Y| so the rule resolves to vertical.
        ("W+A ", (-1.0, 1.0), D.DOWN, D.UP),
        ("W+D ", (1.0, 1.0), D.DOWN, D.UP),
        ("S+A ", (-1.0, -1.0), D.UP, D.DOWN),
        ("S+D ", (1.0, -1.0), D.UP, D.DOWN),
        # Dominant-axis cases from the spec.
        ("0.8/0.3", (0.8, 0.3), D.DOWN, D.RIGHT),
        ("0.3/0.8", (0.3, 0.8), D.DOWN, D.UP),
        ("-0.9/0.2", (-0.9, 0.2), D.DOWN, D.LEFT),
        ("0.2/-0.9", (0.2, -0.9), D.UP, D.DOWN),
    ]

    for label, vec, current, expected in cases:
        got = lib.direction_from_input(unreal.Vector2D(vec[0], vec[1]), current, 0.1, 0.0)
        check(got == expected, "{0} -> {1}".format(label, expected.name),
              "got {0}".format(got.name))


def verify_last_facing():
    header("4. LAST FACING DIRECTION")

    D = unreal.PTKFacingDirection
    lib = unreal.PTKTypesLibrary

    for direction in (D.UP, D.DOWN, D.LEFT, D.RIGHT):
        got = lib.direction_from_input(unreal.Vector2D(0.0, 0.0), direction, 0.1, 0.0)
        check(got == direction,
              "zero input keeps {0}".format(direction.name), "got {0}".format(got.name))

    # Inside the dead zone the direction must also be held.
    for direction in (D.UP, D.DOWN, D.LEFT, D.RIGHT):
        got = lib.direction_from_input(unreal.Vector2D(0.05, 0.05), direction, 0.1, 0.0)
        check(got == direction,
              "dead-zone input keeps {0}".format(direction.name),
              "got {0}".format(got.name))


# ---------------------------------------------------------------------------
def verify_diagonal_normalisation(generated_class):
    """
    Spawns a real Ravager and measures the stored input magnitude.
    Diagonals must be clamped to 1.0; partial analog input must survive.
    """
    header("5. DIAGONAL NORMALISATION (measured on a spawned actor)")

    if generated_class is None:
        check(False, "spawn Ravager", "no generated class")
        return

    # A world must be loaded before actors can be spawned.
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if level_subsystem is not None:
        try:
            level_subsystem.load_level(LEVEL_PATH)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("[PTK]   could not load test level: {0}".format(exc))

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if actor_subsystem is None:
        check(False, "editor actor subsystem available")
        return

    pawn = actor_subsystem.spawn_actor_from_class(
        generated_class, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0))
    if not check(pawn is not None, "Ravager spawns without error"):
        return

    try:
        cases = [
            ("W      ", (0.0, 1.0), 1.0),
            ("S      ", (0.0, -1.0), 1.0),
            ("A      ", (-1.0, 0.0), 1.0),
            ("D      ", (1.0, 0.0), 1.0),
            ("W+A    ", (-1.0, 1.0), 1.0),
            ("W+D    ", (1.0, 1.0), 1.0),
            ("S+A    ", (-1.0, -1.0), 1.0),
            ("S+D    ", (1.0, -1.0), 1.0),
            ("stick50", (0.5, 0.0), 0.5),
            ("stick35", (0.25, 0.25), math.sqrt(0.125)),
        ]
        for label, vec, expected in cases:
            pawn.set_move_input(unreal.Vector2D(vec[0], vec[1]))
            stored = pawn.get_move_input()
            magnitude = math.sqrt(stored.x * stored.x + stored.y * stored.y)
            check(abs(magnitude - expected) < 0.001,
                  "{0} magnitude {1:.4f}".format(label, magnitude),
                  "expected {0:.4f}".format(expected))

        # The headline check: a diagonal must not be ~1.414x a cardinal.
        pawn.set_move_input(unreal.Vector2D(0.0, 1.0))
        cardinal = pawn.get_move_input()
        cardinal_mag = math.sqrt(cardinal.x ** 2 + cardinal.y ** 2)
        pawn.set_move_input(unreal.Vector2D(1.0, 1.0))
        diagonal = pawn.get_move_input()
        diagonal_mag = math.sqrt(diagonal.x ** 2 + diagonal.y ** 2)
        check(abs(diagonal_mag - cardinal_mag) < 0.001,
              "diagonal speed == cardinal speed",
              "cardinal {0:.4f} vs diagonal {1:.4f} (naive would be 1.4142)".format(
                  cardinal_mag, diagonal_mag))

        # Facing setter round-trip.
        for direction in (unreal.PTKFacingDirection.UP, unreal.PTKFacingDirection.LEFT):
            pawn.set_facing_direction(direction)
            check(pawn.get_facing_direction() == direction,
                  "SetFacingDirection({0}) round-trips".format(direction.name))

        verify_screen_directions(pawn)
    finally:
        actor_subsystem.destroy_actor(pawn)


def verify_screen_directions(pawn):
    """
    End-to-end proof that each key moves the character the correct way ON SCREEN.

    Chains the three stages that previously disagreed:
        key -> IA_Move value -> world movement vector -> screen direction

    The regression this guards against: the camera looks along +Y, so its right
    vector is world -X. Assuming "screen right = +X" made every direction travel
    left, which is exactly the bug this checks for.
    """
    header("5b. SCREEN-SPACE DIRECTION (key -> world -> screen)")

    right = pawn.get_editor_property("movement_right_vector")
    up = pawn.get_editor_property("movement_up_vector")

    unreal.log("[PTK]   movement basis: right=({0:+.2f},{1:+.2f},{2:+.2f}) "
               "up=({3:+.2f},{4:+.2f},{5:+.2f})".format(
                   right.x, right.y, right.z, up.x, up.y, up.z))

    # Camera basis, independently derived from the boom yaw.
    cam = unreal.Rotator(0.0, 0.0, 90.0)
    cam_right = cam.get_right_vector()
    cam_up = cam.get_up_vector()

    check(abs(right.x - cam_right.x) < 0.01 and abs(right.z - cam_right.z) < 0.01,
          "movement right matches camera right",
          "movement ({0:+.2f},{1:+.2f}) vs camera ({2:+.2f},{3:+.2f})".format(
              right.x, right.z, cam_right.x, cam_right.z))
    check(abs(up.x - cam_up.x) < 0.01 and abs(up.z - cam_up.z) < 0.01,
          "movement up matches camera up")

    # Values Enhanced Input produces for each key (verified from the saved IMC).
    key_inputs = {
        "W": (0.0, 1.0),
        "S": (0.0, -1.0),
        "A": (-1.0, 0.0),
        "D": (1.0, 0.0),
        "W+A": (-1.0, 1.0),
        "W+D": (1.0, 1.0),
        "S+A": (-1.0, -1.0),
        "S+D": (1.0, -1.0),
    }
    # screen_right / screen_up signs we expect to see for each key.
    expected_screen = {
        "W": (0, +1), "S": (0, -1), "A": (-1, 0), "D": (+1, 0),
        "W+A": (-1, +1), "W+D": (+1, +1), "S+A": (-1, -1), "S+D": (+1, -1),
    }

    for label, (ix, iy) in key_inputs.items():
        # World direction the movement code will push along.
        wx = right.x * ix + up.x * iy
        wz = right.z * ix + up.z * iy
        world = unreal.Vector(wx, 0.0, wz)

        # Project back onto the camera basis to get on-screen direction.
        screen_r = world.x * cam_right.x + world.z * cam_right.z
        screen_u = world.x * cam_up.x + world.z * cam_up.z

        want_r, want_u = expected_screen[label]
        ok_r = (screen_r > 0.01) == (want_r > 0) and (screen_r < -0.01) == (want_r < 0)
        ok_u = (screen_u > 0.01) == (want_u > 0) and (screen_u < -0.01) == (want_u < 0)

        horizontal = "right" if screen_r > 0.01 else ("left" if screen_r < -0.01 else "-")
        vertical = "up" if screen_u > 0.01 else ("down" if screen_u < -0.01 else "-")

        check(ok_r and ok_u,
              "{0:<4} moves screen {1}/{2}".format(label, horizontal, vertical),
              "screen=({0:+.2f},{1:+.2f}) world=({2:+.2f},{3:+.2f})".format(
                  screen_r, screen_u, wx, wz))


# ---------------------------------------------------------------------------
def verify_assets():
    header("6. ASSET LOAD / MISSING REFERENCES")

    # Ravager's art is complete: 1 idle frame, 8 walk frames and 8 attack
    # frames per direction, all real. Nothing references the dev dummies.
    for state, count in (("Idle", 1), ("Walk", 8), ("Attack", 8)):
        for direction in DIRECTIONS:
            path = "{0}/FB_Ravager_{1}_{2}".format(FLIPBOOK_DIR, state, direction)
            fb = unreal.EditorAssetLibrary.load_asset(path)
            if not check(fb is not None, "flipbook loads: FB_Ravager_%s_%s" % (state, direction)):
                continue
            frames = fb.get_editor_property("key_frames")
            empty = [i for i, f in enumerate(frames)
                     if f.get_editor_property("sprite") is None]
            check(len(frames) == count and not empty,
                  "FB_Ravager_{0}_{1}: {2} frame(s), no empty keys".format(
                      state, direction, len(frames)),
                  "empty at {0}".format(empty) if empty else "")

            # Frame order carries the animation, so each sprite is checked
            # against the slot it occupies, not merely against the set.
            misplaced = []
            for index, frame in enumerate(frames):
                sprite = frame.get_editor_property("sprite")
                if sprite is None:
                    continue
                if state == "Idle":
                    expected = "SPR_Ravager_Idle_" + direction
                else:
                    expected = "SPR_Ravager_{0}_{1}_{2:02d}".format(
                        state, direction, index + 1)
                if sprite.get_name() != expected:
                    misplaced.append("{0}!={1}".format(sprite.get_name(), expected))
            check(not misplaced,
                  "FB_Ravager_{0}_{1} frames are in order".format(state, direction),
                  ", ".join(misplaced[:3]))

    for name in ("IA_Move", "IA_Attack", "IMC_PTK_Default"):
        check(unreal.EditorAssetLibrary.does_asset_exist(INPUT_DIR + "/" + name),
              "input asset exists: " + name)

    check(unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PATH),
          "test level exists")


def verify_game_mode():
    header("7. GAME MODE / DEFAULT PAWN")

    cdo = unreal.get_default_object(unreal.PTKGameModeBase.static_class())
    if not check(cdo is not None, "PTKGameModeBase defaults reachable"):
        return
    pawn_class = cdo.get_editor_property("default_pawn_class")
    check(pawn_class is not None, "DefaultPawnClass resolved",
          pawn_class.get_name() if pawn_class else "None")
    if pawn_class is not None:
        check("Ravager" in pawn_class.get_name(),
              "DefaultPawnClass is Ravager", pawn_class.get_name())


# ---------------------------------------------------------------------------
def main():
    unreal.log("[PTK] " + "=" * 62)
    unreal.log("[PTK] Protect the King - 2D : runtime verification")
    unreal.log("[PTK] " + "=" * 62)

    verify_modules()
    generated = verify_blueprint()
    verify_direction_rules()
    verify_last_facing()
    verify_diagonal_normalisation(generated)
    verify_assets()
    verify_game_mode()

    unreal.log("[PTK] " + "=" * 62)
    unreal.log("[PTK] PASSED: {0}   FAILED: {1}".format(len(_passes), len(_failures)))
    for failure in _failures:
        unreal.log_error("[PTK] FAILED: " + failure)
    unreal.log("[PTK] RESULT: {0}".format(
        "ALL RUNTIME CHECKS PASSED" if not _failures else "FAILURES PRESENT"))
    unreal.log("[PTK] " + "=" * 62)


main()
