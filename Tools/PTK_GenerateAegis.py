"""
Protect the King - 2D
Unreal Editor Python script: imports Aegis and wires up the tank guard.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateAegis.py"

What it creates
---------------
  Textures    T_Aegis_*        76 textures, point-filtered, uncompressed
  Sprites     SPR_Aegis_*      76 sprites, pivot (96,179), PPU 1.0
  Flipbooks   FB_Aegis_Idle_*    4 flipbooks, 1 frame  @  8 FPS
              FB_Aegis_Walk_*    4 flipbooks, 8 frames @ 10 FPS
              FB_Aegis_Attack_*  4 flipbooks, 8 frames @ 12 FPS
              FB_Aegis_Death     1 flipbook,  8 frames @  9 FPS
  Blueprint   BP_Aegis         parented to APTKGuardCharacter

Re-running is safe: assets are updated in place, and nothing about Ravager,
Swarm Node, the King or the level is touched.

AEGIS IS A GUARD, NOT A NEW SYSTEM
----------------------------------
BP_Aegis derives from APTKGuardCharacter, the same class Ravager uses. He
therefore inherits, rather than re-implements: the shared UPTKHealthComponent,
facing direction, the Idle/Walk/Attack/Dead state machine, impact-frame melee
timing, the guard's multi-target arc with its once-per-victim rule, player
input and death handling. Only the numbers below differ.

NO IDLE SHEET WAS SUPPLIED
--------------------------
FB_Aegis_Idle_<Dir> holds a SINGLE frame - walk frame 01 of that direction,
which is the cycle's contact pose. Reuse of delivered art, not fabrication.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Contract - matches Tools/ExtractAegisAnimations.py and Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
FRAME_WIDTH = 224
FRAME_HEIGHT = 224
PIVOT_X = 112.0
PIVOT_Y = 200.0
PIXELS_PER_UNREAL_UNIT = 1.0

IDLE_FPS = 8.0
WALK_FPS = 10.0
ATTACK_FPS = 12.0
DEATH_FPS = 9.0

DIRECTIONS = ["Down", "Up", "Left", "Right"]
WALK_FRAME_COUNT = 8
ATTACK_FRAME_COUNT = 8
DEATH_FRAME_COUNT = 8
DEFEND_FRAME_COUNT = 8
DEFEND_FPS = 10.0


# ---------------------------------------------------------------------------
# Prototype balance - Aegis is the tank
# ---------------------------------------------------------------------------
# Ravager: 7000 HP, 25 damage, 3.5 tiles, 240 uu/s - the faster bruiser.
# Aegis:   9000 HP, 20 damage, 3.5 tiles, 200 uu/s - tougher, hits softer,
#          and gives up ground speed for it.
AEGIS_MAX_HP = 9000.0
AEGIS_DAMAGE = 20.0
AEGIS_MOVE_SPEED = 200.0
TILE_SIZE = 64.0
AEGIS_RANGE_TILES = 3.5

# Deliberately identical to Ravager's. The capsule is the combat geometry, so
# keeping it the same means every difference measured between the two guards is
# one of the four numbers above and not an accident of collision size.
AEGIS_COLLISION_RADIUS = 14.0
AEGIS_COLLISION_HALF_HEIGHT = 14.0

# Enhanced Input. A guard spawned by PTKPlayGuard is a fresh actor, so it can
# only be driven from the keyboard if its own Blueprint carries these - the
# player controller does not lend them out. Without them Aegis still moved
# whenever a test script called SetMoveInput, which is exactly how a guard can
# look tested and still be unplayable by hand.
INPUT_DIR = "/Game/PTK/Input"
MAPPING_CONTEXT = INPUT_DIR + "/IMC_PTK_Default"
MOVE_ACTION = INPUT_DIR + "/IA_Move"
ATTACK_ACTION = INPUT_DIR + "/IA_Attack"
# The shield brace runs 8 frames at 10 FPS = 0.8s, and that duration IS the
# skill: damage is blocked for exactly as long as the animation plays, so the
# window the player sees is the window they get.
DEFEND_ACTION = INPUT_DIR + "/IA_Defend"

# Two bindings for one action - a block wants to be reachable without moving the
# hand off the movement keys, and with the mouse for anyone who plays that way.
DEFEND_KEYS = ("LeftShift", "RightMouseButton")

AEGIS_ROOT = "/Game/PTK/Characters/Guards/Aegis"
TEXTURE_DIR = AEGIS_ROOT + "/Textures"
SPRITE_DIR = AEGIS_ROOT + "/Sprites"
FLIPBOOK_DIR = AEGIS_ROOT + "/Flipbooks"
BLUEPRINT_DIR = AEGIS_ROOT + "/Blueprints"

_asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
_summary = {"textures": 0, "sprites": 0, "flipbooks": 0, "blueprint": 0,
            "warnings": [], "errors": []}


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


def project_dir():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())


def ensure_directory(path):
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)


def frame_layout():
    """(asset stem, path relative to Frames/) for all 76 delivered frames."""
    layout = []
    for direction in DIRECTIONS:
        name = "Idle_{0}".format(direction)
        layout.append((name, os.path.join("Idle", name + ".png")))
    for anim, count in (("Walk", WALK_FRAME_COUNT), ("Attack", ATTACK_FRAME_COUNT)):
        for direction in DIRECTIONS:
            for index in range(1, count + 1):
                name = "{0}_{1}_{2:02d}".format(anim, direction, index)
                layout.append((name, os.path.join(anim, direction, name + ".png")))
    for index in range(1, DEATH_FRAME_COUNT + 1):
        name = "Death_{0:02d}".format(index)
        layout.append((name, os.path.join("Death", name + ".png")))
    for direction in DIRECTIONS:
        for index in range(1, DEFEND_FRAME_COUNT + 1):
            name = "Defend_{0}_{1:02d}".format(direction, index)
            layout.append((name, os.path.join("Defend", direction, name + ".png")))
    return layout


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures():
    ensure_directory(TEXTURE_DIR)
    root = os.path.join(project_dir(), "ArtSource", "Characters", "Guards",
                        "Aegis", "Frames")

    tasks = []
    wanted = []
    for stem, relative in frame_layout():
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            fail("missing source frame " + relative)
            continue
        asset_name = "T_Aegis_" + stem
        wanted.append(asset_name)

        task = unreal.AssetImportTask()
        task.set_editor_property("filename", full)
        task.set_editor_property("destination_path", TEXTURE_DIR)
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        tasks.append(task)

    if tasks:
        _asset_tools.import_asset_tasks(tasks)

    textures = {}
    for asset_name in wanted:
        texture = unreal.EditorAssetLibrary.load_asset(TEXTURE_DIR + "/" + asset_name)
        if texture is None:
            fail("texture failed to import: " + asset_name)
            continue
        # Pixel-art import rules, identical to every other PTK character.
        set_prop(texture, "filter", unreal.TextureFilter.TF_NEAREST)
        set_prop(texture, "mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        set_prop(texture, "compression_settings",
                 unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        set_prop(texture, "srgb", True)
        set_prop(texture, "never_stream", True)
        set_prop(texture, "lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
        textures[asset_name] = texture
        _summary["textures"] += 1

    info("textures ready: {0}".format(len(textures)))
    return textures


# ---------------------------------------------------------------------------
# 2. Sprites
# ---------------------------------------------------------------------------
def create_sprites(textures):
    ensure_directory(SPRITE_DIR)
    sprites = {}
    factory = unreal.PaperSpriteFactory()

    for texture_name, texture in sorted(textures.items()):
        sprite_name = "SPR_" + texture_name[len("T_"):]
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/" + sprite_name)
        if sprite is None:
            sprite = _asset_tools.create_asset(
                sprite_name, SPRITE_DIR, unreal.PaperSprite, factory)
        if sprite is None:
            fail("could not create sprite " + sprite_name)
            continue

        set_prop(sprite, "source_texture", texture)
        set_prop(sprite, "source_uv", unreal.Vector2D(0.0, 0.0))
        set_prop(sprite, "source_dimension",
                 unreal.Vector2D(float(FRAME_WIDTH), float(FRAME_HEIGHT)))
        set_prop(sprite, "pixels_per_unreal_unit", PIXELS_PER_UNREAL_UNIT)
        set_prop(sprite, "pivot_mode", unreal.SpritePivotMode.CUSTOM)
        set_prop(sprite, "custom_pivot_point", unreal.Vector2D(PIVOT_X, PIVOT_Y))
        set_prop(sprite, "snap_pivot_to_pixel_grid", True)
        set_prop(sprite, "sprite_collision_domain", unreal.SpriteCollisionMode.NONE)

        unreal.EditorAssetLibrary.save_loaded_asset(sprite, only_if_is_dirty=False)
        sprites[sprite_name] = sprite
        _summary["sprites"] += 1

    info("sprites ready: {0}".format(len(sprites)))
    return sprites


# ---------------------------------------------------------------------------
# 3. Flipbooks
# ---------------------------------------------------------------------------
def create_flipbooks(sprites):
    ensure_directory(FLIPBOOK_DIR)
    flipbooks = {}
    factory = unreal.PaperFlipbookFactory()

    def build(name, sprite_names, fps):
        frames = []
        for sprite_name in sprite_names:
            sprite = sprites.get(sprite_name)
            if sprite is None:
                fail("flipbook {0} is missing sprite {1}".format(name, sprite_name))
                return None
            key = unreal.PaperFlipbookKeyFrame()
            key.set_editor_property("sprite", sprite)
            key.set_editor_property("frame_run", 1)
            frames.append(key)

        flipbook = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
        if flipbook is None:
            flipbook = _asset_tools.create_asset(
                name, FLIPBOOK_DIR, unreal.PaperFlipbook, factory)
        if flipbook is None:
            fail("could not create flipbook " + name)
            return None
        set_prop(flipbook, "frames_per_second", fps)
        set_prop(flipbook, "key_frames", frames)
        unreal.EditorAssetLibrary.save_loaded_asset(flipbook, only_if_is_dirty=False)
        _summary["flipbooks"] += 1
        return flipbook

    for anim, count, fps in (("Walk", WALK_FRAME_COUNT, WALK_FPS),
                             ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS)):
        for direction in DIRECTIONS:
            name = "FB_Aegis_{0}_{1}".format(anim, direction)
            fb = build(name, ["SPR_Aegis_{0}_{1}_{2:02d}".format(anim, direction, i)
                              for i in range(1, count + 1)], fps)
            if fb:
                flipbooks[name] = fb

    for direction in DIRECTIONS:
        name = "FB_Aegis_Idle_" + direction
        fb = build(name, ["SPR_Aegis_Idle_" + direction], IDLE_FPS)
        if fb:
            flipbooks[name] = fb

    for direction in DIRECTIONS:
        name = "FB_Aegis_Defend_" + direction
        fb = build(name, ["SPR_Aegis_Defend_{0}_{1:02d}".format(direction, i)
                          for i in range(1, DEFEND_FRAME_COUNT + 1)], DEFEND_FPS)
        if fb:
            flipbooks[name] = fb

    death = build("FB_Aegis_Death",
                  ["SPR_Aegis_Death_{0:02d}".format(i)
                   for i in range(1, DEATH_FRAME_COUNT + 1)], DEATH_FPS)
    if death:
        flipbooks["FB_Aegis_Death"] = death

    info("flipbooks ready: {0}".format(len(flipbooks)))
    return flipbooks


# ---------------------------------------------------------------------------
# 4. Blueprint
# ---------------------------------------------------------------------------
def directional(flipbooks, prefix):
    value = unreal.PTKDirectionalFlipbooks()
    for direction in DIRECTIONS:
        value.set_editor_property(direction.lower(), flipbooks.get(prefix + direction))
    return value


def ensure_defend_input():
    """
    Creates IA_Defend and binds it in the shared mapping context.

    The mapping context is shared by every guard, but only a character whose
    Blueprint carries DefendAction ever binds a handler to it - so adding the
    entry here changes nothing for Ravager or Wraith, who have no shield.

    Idempotent: the action's existing keys are cleared before remapping, so
    re-running cannot stack duplicate bindings.
    """
    action = unreal.EditorAssetLibrary.load_asset(DEFEND_ACTION)
    if action is None:
        action = _asset_tools.create_asset(
            "IA_Defend", INPUT_DIR, unreal.InputAction, None)
        if action is None:
            fail("could not create IA_Defend")
            return None
        # Digital, like IA_Attack: pressed or not, no axis.
        set_prop(action, "value_type", unreal.InputActionValueType.BOOLEAN)
        unreal.EditorAssetLibrary.save_loaded_asset(action, only_if_is_dirty=False)
        info("created IA_Defend")

    context = unreal.EditorAssetLibrary.load_asset(MAPPING_CONTEXT)
    if context is None:
        warn("mapping context missing: " + MAPPING_CONTEXT)
        return action

    try:
        context.unmap_all_keys_from_action(action)
        for key_name in DEFEND_KEYS:
            # FKey has a custom serialiser, so it is built by setting the
            # property rather than by passing the name to the constructor -
            # unreal.Key() takes no arguments in 5.8.
            key = unreal.Key()
            key.set_editor_property("key_name", key_name)
            context.map_key(action, key)
        unreal.EditorAssetLibrary.save_loaded_asset(context, only_if_is_dirty=False)
        info("IA_Defend bound to " + ", ".join(DEFEND_KEYS))
    except Exception as exc:  # noqa: BLE001
        warn("could not bind IA_Defend keys: {0}".format(exc))
    return action


def create_blueprint(flipbooks, defend_action):
    guard_class = getattr(unreal, "PTKGuardCharacter", None)
    if guard_class is None:
        fail("APTKGuardCharacter is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_Aegis"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", guard_class)
        blueprint = _asset_tools.create_asset(
            "BP_Aegis", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_Aegis")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Aegis class defaults")
        return blueprint

    set_prop(cdo, "idle_flipbooks", directional(flipbooks, "FB_Aegis_Idle_"))
    set_prop(cdo, "walk_flipbooks", directional(flipbooks, "FB_Aegis_Walk_"))
    set_prop(cdo, "attack_flipbooks", directional(flipbooks, "FB_Aegis_Attack_"))
    set_prop(cdo, "death_flipbook", flipbooks.get("FB_Aegis_Death"))
    set_prop(cdo, "defend_flipbooks", directional(flipbooks, "FB_Aegis_Defend_"))
    if defend_action is not None:
        set_prop(cdo, "defend_action", defend_action)

    set_prop(cdo, "max_move_speed", AEGIS_MOVE_SPEED)
    set_prop(cdo, "attack_damage", AEGIS_DAMAGE)
    set_prop(cdo, "tile_size", TILE_SIZE)
    set_prop(cdo, "attack_range_tiles", AEGIS_RANGE_TILES)
    set_prop(cdo, "collision_radius", AEGIS_COLLISION_RADIUS)
    set_prop(cdo, "collision_half_height", AEGIS_COLLISION_HALF_HEIGHT)
    set_prop(cdo, "default_facing_direction", unreal.PTKFacingDirection.DOWN)

    # Identity, so the health panel and the defeat banner name the guard being
    # played rather than falling back to a generic label.
    set_prop(cdo, "guard_id", "Aegis")
    set_prop(cdo, "guard_display_name", "Aegis")

    for prop, path in (("default_mapping_context", MAPPING_CONTEXT),
                       ("move_action", MOVE_ACTION),
                       ("attack_action", ATTACK_ACTION)):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            warn("input asset missing: " + path)
            continue
        set_prop(cdo, prop, asset)

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", AEGIS_MAX_HP)
    else:
        warn("could not reach BP_Aegis's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Aegis did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Aegis ready")
    return blueprint


# ---------------------------------------------------------------------------
# 5. Verification
# ---------------------------------------------------------------------------
def verify():
    info("")
    info("-" * 62)
    info("verification")
    ok = True

    pivots = set()
    dims = set()
    total = 0
    for stem, _relative in frame_layout():
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/SPR_Aegis_" + stem)
        if sprite is None:
            ok = False
            fail("missing sprite SPR_Aegis_" + stem)
            continue
        total += 1
        pivot = sprite.get_editor_property("custom_pivot_point")
        pivots.add((round(pivot.x), round(pivot.y)))
        dimension = sprite.get_editor_property("source_dimension")
        dims.add((round(dimension.x), round(dimension.y)))

    if pivots == {(int(PIVOT_X), int(PIVOT_Y))}:
        info("PASS  {0} sprites share the pivot ({1}, {2})".format(
            total, int(PIVOT_X), int(PIVOT_Y)))
    else:
        ok = False
        fail("inconsistent sprite pivots: {0}".format(pivots))

    if dims == {(FRAME_WIDTH, FRAME_HEIGHT)}:
        info("PASS  {0} sprites are {1}x{2}".format(total, FRAME_WIDTH, FRAME_HEIGHT))
    else:
        ok = False
        fail("inconsistent sprite dimensions: {0}".format(dims))

    expected = [("Idle", 1, IDLE_FPS), ("Walk", WALK_FRAME_COUNT, WALK_FPS),
                ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS),
                ("Defend", DEFEND_FRAME_COUNT, DEFEND_FPS)]
    for anim, count, fps in expected:
        for direction in DIRECTIONS:
            name = "FB_Aegis_{0}_{1}".format(anim, direction)
            fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
            if fb is None:
                ok = False
                fail("missing " + name)
                continue
            keys = fb.get_editor_property("key_frames")
            if len(keys) != count:
                ok = False
                fail("{0} has {1} frames, expected {2}".format(name, len(keys), count))
    death = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/FB_Aegis_Death")
    if death is None or len(death.get_editor_property("key_frames")) != DEATH_FRAME_COUNT:
        ok = False
        fail("FB_Aegis_Death missing or wrong length")
    if ok:
        info("PASS  17 flipbooks: 4 idle, 4 walk, 4 attack, 4 defend, 1 death")

    blueprint = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_Aegis")
    if blueprint is None:
        ok = False
        fail("BP_Aegis missing")
    else:
        cdo = unreal.get_default_object(blueprint.generated_class())
        health = cdo.get_editor_property("health_component")
        hp = health.get_editor_property("max_health") if health else 0.0
        checks = [("attack_damage", AEGIS_DAMAGE),
                  ("max_move_speed", AEGIS_MOVE_SPEED),
                  ("attack_range_tiles", AEGIS_RANGE_TILES),
                  ("tile_size", TILE_SIZE)]
        for prop, want in checks:
            got = cdo.get_editor_property(prop)
            if abs(got - want) > 0.01:
                ok = False
                fail("BP_Aegis {0} is {1}, expected {2}".format(prop, got, want))
        if abs(hp - AEGIS_MAX_HP) > 0.01:
            ok = False
            fail("BP_Aegis MaxHealth is {0}, expected {1}".format(hp, AEGIS_MAX_HP))
        for prop in ("idle_flipbooks", "walk_flipbooks", "attack_flipbooks",
                     "defend_flipbooks"):
            value = cdo.get_editor_property(prop)
            missing = [d for d in DIRECTIONS
                       if value.get_editor_property(d.lower()) is None]
            if missing:
                ok = False
                fail("BP_Aegis {0} missing {1}".format(prop, missing))
        if cdo.get_editor_property("death_flipbook") is None:
            ok = False
            fail("BP_Aegis has no death flipbook")
        if cdo.get_editor_property("defend_action") is None:
            ok = False
            fail("BP_Aegis has no defend_action - the shield key would do nothing")
        for prop in ("default_mapping_context", "move_action", "attack_action"):
            if cdo.get_editor_property(prop) is None:
                ok = False
                fail("BP_Aegis has no {0} - WASD would not reach him".format(prop))
        if ok:
            info("PASS  BP_Aegis: {0:.0f} HP, {1:.0f} damage, {2} tiles ({3:.0f} uu), "
                 "speed {4:.0f}".format(hp, AEGIS_DAMAGE, AEGIS_RANGE_TILES,
                                        AEGIS_RANGE_TILES * TILE_SIZE, AEGIS_MOVE_SPEED))
            # The point of the whole phase: Aegis IS a guard, not a parallel
            # implementation. Proven by type, not by the asset's metadata.
            if isinstance(cdo, unreal.PTKGuardCharacter):
                info("PASS  BP_Aegis is an APTKGuardCharacter - same class as Ravager, "
                     "so health, facing, melee timing and death are inherited")
            else:
                ok = False
                fail("BP_Aegis does not derive from APTKGuardCharacter")

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("Aegis generation")
    info("=" * 62)

    textures = import_textures()
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    defend_action = ensure_defend_input()
    create_blueprint(flipbooks, defend_action)
    verify()

    info("=" * 62)
    for key in ("textures", "sprites", "flipbooks", "blueprint"):
        info("{0:<10}: {1}".format(key, _summary[key]))
    info("{0:<10}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<10}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
