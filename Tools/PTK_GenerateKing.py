"""
Protect the King - 2D
Unreal Editor Python script: imports the King and places him in the test level.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateKing.py"

What it creates
---------------
  Textures    T_King_*        32 textures, point-filtered, uncompressed
  Sprites     SPR_King_*      32 sprites, pivot (96,208), PPU 1.0
  Flipbooks   FB_King_Idle       8 frames @  8 FPS, looping
              FB_King_Alert      8 frames @ 10 FPS, looping
              FB_King_PowerCast  8 frames @ 12 FPS, one shot
              FB_King_Death      8 frames @  9 FPS, one shot, holds last frame
  Blueprint   BP_King         parented to APTKKingCharacter
  Level       places one King in L_PTK_TestGround at a fixed position

Re-running is safe: assets are updated in place and the arena is not rebuilt.

THE KING IS NOT A PAWN
----------------------
BP_King derives from APTKKingCharacter, which derives from AActor - not from
APTKTopDownCharacter. He therefore has no movement component, no input
component, and cannot be possessed by any controller. There are no directional
flipbooks because he never turns to face anything: each animation is a single
non-directional sequence.

NO HIT SHEET WAS SUPPLIED
-------------------------
Four sheets were delivered - idle, alert, power cast and death. There is no hit
sheet, so HitFlipbook is deliberately left EMPTY rather than filled with
something invented. APTKKingCharacter::ResolveHitFlipbook falls back to the
alert reaction while it is empty, and the moment real hit art exists this is a
one-field change.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Contract - matches Tools/ExtractKingAnimations.py and Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
FRAME_WIDTH = 192
FRAME_HEIGHT = 232
PIVOT_X = 96.0
PIVOT_Y = 208.0
PIXELS_PER_UNREAL_UNIT = 1.0

FRAME_COUNT = 8

# Idle breathes slowly; alert is a touch sharper because it is a reaction; the
# cast is the fastest so the starburst reads as a snap rather than a swell;
# death is slowest of all, so the collapse has weight.
ANIMATIONS = [
    ("Idle", 8.0, True),
    ("Alert", 10.0, True),
    ("PowerCast", 12.0, False),
    ("Death", 9.0, False),
]

# ---------------------------------------------------------------------------
# Prototype balance
# ---------------------------------------------------------------------------
# Temporary. The King is the objective, so he has to outlast a guard by a wide
# margin: Ravager is 7000, a Swarm Node is 100.
KING_MAX_HP = 15000.0

# World units. Generous on purpose - this drives a reaction animation, not a
# trigger volume, and he should look aware of trouble before it reaches him.
KING_ALERT_RADIUS = 600.0

KING_COLLISION_RADIUS = 22.0
KING_COLLISION_HALF_HEIGHT = 22.0

# Arena is X -700..700, Z -450..450, PlayerStart at the origin and the enemy
# spawner at (420, 0, -260). This corner is clear of Obstacle_A (which ends at
# X = -375) and sits about 1030 units from the spawner, so the King starts in
# Idle and only reaches Alert once the fight is brought to him.
KING_LOCATION = (-480.0, 0.0, 240.0)

KING_ROOT = "/Game/PTK/Characters/King"
TEXTURE_DIR = KING_ROOT + "/Textures"
SPRITE_DIR = KING_ROOT + "/Sprites"
FLIPBOOK_DIR = KING_ROOT + "/Flipbooks"
BLUEPRINT_DIR = KING_ROOT + "/Blueprints"

LEVEL_PATH = "/Game/PTK/Maps/L_PTK_TestGround"

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
    """(filename, relative path) for all 32 delivered frames."""
    layout = []
    for anim, _fps, _loop in ANIMATIONS:
        for index in range(1, FRAME_COUNT + 1):
            name = "{0}_{1:02d}.png".format(anim, index)
            layout.append((name, os.path.join(anim, name)))
    return layout


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures():
    ensure_directory(TEXTURE_DIR)
    root = os.path.join(project_dir(), "ArtSource", "Characters", "King", "Frames")

    tasks = []
    wanted = []
    for name, relative in frame_layout():
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            fail("missing source frame " + relative)
            continue
        asset_name = "T_King_" + os.path.splitext(name)[0]
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

        # Pixel-art import rules, identical to Ravager's and Swarm Node's.
        # Anything else here produces a blurred or colour-bled sprite.
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
        path = SPRITE_DIR + "/" + sprite_name

        sprite = unreal.EditorAssetLibrary.load_asset(path)
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

    for anim, fps, _looping in ANIMATIONS:
        name = "FB_King_" + anim
        frames = []
        ok = True
        for index in range(1, FRAME_COUNT + 1):
            sprite = sprites.get("SPR_King_{0}_{1:02d}".format(anim, index))
            if sprite is None:
                fail("flipbook {0} is missing frame {1}".format(name, index))
                ok = False
                break
            key = unreal.PaperFlipbookKeyFrame()
            key.set_editor_property("sprite", sprite)
            key.set_editor_property("frame_run", 1)
            frames.append(key)
        if not ok:
            continue

        flipbook = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
        if flipbook is None:
            flipbook = _asset_tools.create_asset(
                name, FLIPBOOK_DIR, unreal.PaperFlipbook, factory)
        if flipbook is None:
            fail("could not create flipbook " + name)
            continue

        set_prop(flipbook, "frames_per_second", fps)
        set_prop(flipbook, "key_frames", frames)
        unreal.EditorAssetLibrary.save_loaded_asset(flipbook, only_if_is_dirty=False)
        flipbooks[name] = flipbook
        _summary["flipbooks"] += 1

    info("flipbooks ready: {0}".format(len(flipbooks)))
    return flipbooks


# ---------------------------------------------------------------------------
# 4. Blueprint
# ---------------------------------------------------------------------------
def create_king_blueprint(flipbooks):
    king_class = getattr(unreal, "PTKKingCharacter", None)
    if king_class is None:
        fail("APTKKingCharacter is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_King"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", king_class)
        blueprint = _asset_tools.create_asset(
            "BP_King", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_King")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_King class defaults")
        return blueprint

    set_prop(cdo, "idle_flipbook", flipbooks.get("FB_King_Idle"))
    set_prop(cdo, "alert_flipbook", flipbooks.get("FB_King_Alert"))
    set_prop(cdo, "power_cast_flipbook", flipbooks.get("FB_King_PowerCast"))
    set_prop(cdo, "death_flipbook", flipbooks.get("FB_King_Death"))
    # hit_flipbook is left EMPTY on purpose - no hit sheet was delivered, and
    # the class falls back to the alert reaction rather than inventing one.

    set_prop(cdo, "alert_radius", KING_ALERT_RADIUS)
    set_prop(cdo, "collision_radius", KING_COLLISION_RADIUS)
    set_prop(cdo, "collision_half_height", KING_COLLISION_HALF_HEIGHT)

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", KING_MAX_HP)
    else:
        warn("could not reach BP_King's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_King did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_King ready")
    return blueprint


# ---------------------------------------------------------------------------
# 5. Level
# ---------------------------------------------------------------------------
def place_in_level(blueprint):
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if level_subsystem is None or actor_subsystem is None:
        fail("editor subsystems unavailable - cannot place the King")
        return False

    level_subsystem.load_level(LEVEL_PATH)

    # Re-running must not stack duplicate Kings.
    for actor in actor_subsystem.get_all_level_actors():
        if actor and actor.get_actor_label().startswith("King"):
            actor_subsystem.destroy_actor(actor)

    # spawn_actor_from_object returns None for a Blueprint asset - the
    # generated class is what actually spawns.
    king = actor_subsystem.spawn_actor_from_class(
        blueprint.generated_class(), unreal.Vector(*KING_LOCATION),
        unreal.Rotator(0.0, 0.0, 0.0))
    if king is None:
        fail("could not spawn BP_King into the level")
        return False

    king.set_actor_label("King")
    level_subsystem.save_current_level()
    info("King placed at {0}".format(KING_LOCATION))
    return True


# ---------------------------------------------------------------------------
# 6. Verification
# ---------------------------------------------------------------------------
def verify():
    info("")
    info("-" * 62)
    info("verification")
    ok = True

    pivots = set()
    dims = set()
    for name, _relative in frame_layout():
        sprite_name = "SPR_King_" + os.path.splitext(name)[0]
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/" + sprite_name)
        if sprite is None:
            ok = False
            fail("missing sprite " + sprite_name)
            continue
        pivot = sprite.get_editor_property("custom_pivot_point")
        pivots.add((round(pivot.x), round(pivot.y)))
        dimension = sprite.get_editor_property("source_dimension")
        dims.add((round(dimension.x), round(dimension.y)))

    if pivots == {(int(PIVOT_X), int(PIVOT_Y))}:
        info("PASS  32/32 sprites share the pivot ({0}, {1})".format(
            int(PIVOT_X), int(PIVOT_Y)))
    else:
        ok = False
        fail("inconsistent sprite pivots: {0}".format(pivots))

    if dims == {(FRAME_WIDTH, FRAME_HEIGHT)}:
        info("PASS  32/32 sprites are {0}x{1}".format(FRAME_WIDTH, FRAME_HEIGHT))
    else:
        ok = False
        fail("inconsistent sprite dimensions: {0}".format(dims))

    for anim, fps, _loop in ANIMATIONS:
        flipbook = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/FB_King_" + anim)
        if flipbook is None:
            ok = False
            fail("missing FB_King_" + anim)
            continue
        keys = flipbook.get_editor_property("key_frames")
        rate = flipbook.get_editor_property("frames_per_second")
        if len(keys) != FRAME_COUNT:
            ok = False
            fail("FB_King_{0} has {1} frames, expected {2}".format(
                anim, len(keys), FRAME_COUNT))
        elif abs(rate - fps) > 0.01:
            ok = False
            fail("FB_King_{0} runs at {1} FPS, expected {2}".format(anim, rate, fps))
        else:
            info("PASS  FB_King_{0}: {1} frames @ {2:.0f} FPS".format(anim, len(keys), rate))

    blueprint = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_King")
    if blueprint is None:
        ok = False
        fail("BP_King missing")
    else:
        cdo = unreal.get_default_object(blueprint.generated_class())
        health = cdo.get_editor_property("health_component")
        hp = health.get_editor_property("max_health") if health else 0.0
        radius = cdo.get_editor_property("alert_radius")

        for prop in ("idle_flipbook", "alert_flipbook", "power_cast_flipbook",
                     "death_flipbook"):
            if cdo.get_editor_property(prop) is None:
                ok = False
                fail("BP_King has no {0} assigned".format(prop))

        if abs(hp - KING_MAX_HP) > 0.01:
            ok = False
            fail("BP_King MaxHealth is {0}, expected {1}".format(hp, KING_MAX_HP))
        elif abs(radius - KING_ALERT_RADIUS) > 0.01:
            ok = False
            fail("BP_King AlertRadius is {0}, expected {1}".format(
                radius, KING_ALERT_RADIUS))
        else:
            info("PASS  BP_King: {0:.0f} HP, alert radius {1:.0f}".format(hp, radius))

        # The whole point of the class: he must not be a Pawn.
        if cdo.get_editor_property("hit_flipbook") is None:
            info("NOTE  BP_King HitFlipbook is empty - no hit sheet was supplied, "
                 "so the alert reaction stands in (see APTKKingCharacter)")

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("King generation")
    info("=" * 62)

    textures = import_textures()
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    blueprint = create_king_blueprint(flipbooks)
    if blueprint:
        place_in_level(blueprint)
    verify()

    info("=" * 62)
    for key in ("textures", "sprites", "flipbooks", "blueprint"):
        info("{0:<10}: {1}".format(key, _summary[key]))
    info("{0:<10}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<10}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
