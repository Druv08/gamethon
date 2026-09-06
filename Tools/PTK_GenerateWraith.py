"""
Protect the King - 2D
Unreal Editor Python script: imports Wraith and wires up the ranged guard.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateWraith.py"

What it creates
---------------
  Textures    T_Wraith_*         91 textures, point-filtered, uncompressed
  Sprites     SPR_Wraith_*       91 sprites
                                 76 character, pivot (96,179)
                                 15 projectile, pivot (64,64) - see below
  Flipbooks   FB_Wraith_Idle_*     4 flipbooks, 1 frame  @  8 FPS
              FB_Wraith_Walk_*     4 flipbooks, 8 frames @ 10 FPS
              FB_Wraith_Attack_*   4 flipbooks, 8 frames @ 12 FPS
              FB_Wraith_Death      1 flipbook,  8 frames @  9 FPS
              FB_Wraith_Arrow_*    4 flipbooks, 3 frames @ 12 FPS
              FB_Wraith_Impact     1 flipbook,  3 frames @ 12 FPS
  Blueprints  BP_Arrow_Wraith    parented to APTKProjectile
              BP_Wraith          parented to APTKGuardCharacter

Re-running is safe: assets are updated in place, and nothing about Ravager,
Aegis, Swarm Node, the King or the level is touched.


WRAITH IS A GUARD, NOT A NEW SYSTEM
-----------------------------------
BP_Wraith derives from APTKGuardCharacter, the same class Ravager and Aegis
use. He therefore inherits, rather than re-implements: the shared
UPTKHealthComponent, facing direction, the Idle/Walk/Attack/Dead state machine,
attack timing and its facing lock, player input, death handling, and the fact
that enemies recognise him as a guard to be targeted.

What is genuinely new is the RANGED path, and that was added to the shared base
rather than to Wraith - APTKTopDownCharacter fires a projectile instead of
running the melee sphere whenever ProjectileClass is set. Wraith just sets it.
A ranged Sentinel, or a ranged enemy, inherits the same path by setting the
same property, with no new code at all.


THE ARROW PIVOT IS THE CENTRE, NOT THE FEET
-------------------------------------------
Every character sprite in this project pivots on the feet, because that is what
makes a character stand on a point. A projectile has no feet: it pivots on its
own centre, so the actor location IS the arrow, which is what makes the flight
sweep, the impact position and the drawn sprite agree with one another.

The arrow canvas is 129x129 - odd, so there is a true centre pixel at (64,64).
That is what lets the four directions be exact 90-degree rotations of one
drawing rather than a runtime rotation of a sprite, which would resample pixel
art. The rotations are baked by Tools/ExtractWraithAnimations.py.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Contract - matches Tools/ExtractWraithAnimations.py and Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
FRAME_WIDTH = 224
FRAME_HEIGHT = 224
PIVOT_X = 112.0
PIVOT_Y = 200.0
PIXELS_PER_UNREAL_UNIT = 1.0

ARROW_SIZE = 129
ARROW_PIVOT = 64.0

IDLE_FPS = 8.0
WALK_FPS = 10.0
ATTACK_FPS = 12.0
DEATH_FPS = 9.0
ARROW_FPS = 12.0
IMPACT_FPS = 12.0

DIRECTIONS = ["Down", "Up", "Left", "Right"]
WALK_FRAME_COUNT = 8
ATTACK_FRAME_COUNT = 8
DEATH_FRAME_COUNT = 8
ARROW_FRAME_COUNT = 3
IMPACT_FRAME_COUNT = 3

# ---------------------------------------------------------------------------
# Prototype balance - Wraith is the ranged skirmisher
# ---------------------------------------------------------------------------
# Ravager: 7000 HP, 25 damage, 240 uu/s, 3.5 tiles - the bruiser.
# Aegis:   9000 HP, 20 damage, 200 uu/s, 3.5 tiles - the tank.
# Wraith:  5000 HP, 30 damage, 270 uu/s, 7.0 tiles - fragile, quick, and the
#          only one who can hurt something that is not already on top of him.
WRAITH_MAX_HP = 5000.0
# Back to 30 on request, after a spell at 50. With the blast below, 50 let two
# arrows clear an entire wave, which put him far ahead of every other guard.
WRAITH_DAMAGE = 30.0
WRAITH_MOVE_SPEED = 270.0
TILE_SIZE = 64.0
WRAITH_RANGE_TILES = 7.0

# Deliberately identical to Ravager's and Aegis's. The capsule is the combat
# geometry, so keeping it the same means every measured difference between the
# guards is one of the numbers above and not an accident of collision size.
WRAITH_COLLISION_RADIUS = 14.0
WRAITH_COLLISION_HALF_HEIGHT = 14.0

# The arrow leaves the bow on frame 6 of 8. Frame 6 begins at 5/8 of the
# animation, hence 0.625 - read off the artwork, where frames 1-5 draw the bow
# with the arrow still nocked and frame 6 is the first with the string released.
# Ravager and Aegis use 0.5 because their impact pose is frame 5.
WRAITH_RELEASE_FRACTION = 0.625

# 900 uu/s crosses the full 7 tiles in half a second: fast enough to read as an
# arrow rather than a thrown rock, slow enough that you can see it travel and
# watch it miss something that moved.
ARROW_SPEED = 900.0

# Widened from 8. The arrow has to pass this close to a body to connect at all,
# and 8 was a needle - it asked for pixel-accurate aim in a game where the
# enemies are a moving crowd.
ARROW_COLLISION_RADIUS = 12.0

# ZERO: one arrow, one enemy.
#
# He briefly carried a 1.5-tile blast, which made a single shot clear most of a
# wave and put him far ahead of every other guard. He is the single-target
# marksman again; the burst belongs to Sentinel, who is the mage. Zero is
# handled as its own case in APTKProjectile - even a tiny radius would still
# catch an enemy capsule pressed against the one that was struck.
ARROW_SPLASH_RADIUS = 0.0

# Measured off the finished attack frames, where the nocked arrow's centroid
# sits 64-82 px above the feet (mean 72) and about 33 px forward in profile.
#
# MUZZLE_HEIGHT is now VISUAL ONLY - it lifts the arrow's sprite to the bow but
# leaves the actor on the combat row. Flying at 70 put the arrow above every
# enemy's collision blob: measured over 104 live shots, level shots connected
# 32% of the time and upward shots 10%.
MUZZLE_FORWARD = 30.0
MUZZLE_HEIGHT = 70.0

# 3 frames at 12 FPS is 0.25s; the lifetime gives it room to finish.
IMPACT_LIFETIME = 0.3

# Enhanced Input. A guard spawned by PTKPlayGuard is a fresh actor, so it can
# only be driven from the keyboard if its own Blueprint carries these - the
# player controller does not lend them out. Without them the character still
# moves when a script calls SetMoveInput, which is exactly how a guard can look
# tested and still be unplayable by hand.
INPUT_DIR = "/Game/PTK/Input"
MAPPING_CONTEXT = INPUT_DIR + "/IMC_PTK_Default"
MOVE_ACTION = INPUT_DIR + "/IA_Move"
ATTACK_ACTION = INPUT_DIR + "/IA_Attack"

WRAITH_ROOT = "/Game/PTK/Characters/Guards/Wraith"
TEXTURE_DIR = WRAITH_ROOT + "/Textures"
SPRITE_DIR = WRAITH_ROOT + "/Sprites"
FLIPBOOK_DIR = WRAITH_ROOT + "/Flipbooks"
BLUEPRINT_DIR = WRAITH_ROOT + "/Blueprints"

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


def character_layout():
    """(asset stem, path relative to Frames/) for the 76 character frames."""
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
    return layout


def projectile_layout():
    """(asset stem, path relative to Frames/) for the 15 projectile frames."""
    layout = []
    for direction in DIRECTIONS:
        for index in range(1, ARROW_FRAME_COUNT + 1):
            name = "Arrow_{0}_{1:02d}".format(direction, index)
            layout.append((name, os.path.join("Arrow", direction, name + ".png")))
    for index in range(1, IMPACT_FRAME_COUNT + 1):
        name = "Impact_{0:02d}".format(index)
        layout.append((name, os.path.join("Impact", name + ".png")))
    return layout


def full_layout():
    return character_layout() + projectile_layout()


def is_projectile(stem):
    return stem.startswith("Arrow_") or stem.startswith("Impact_")


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures():
    ensure_directory(TEXTURE_DIR)
    root = os.path.join(project_dir(), "ArtSource", "Characters", "Guards",
                        "Wraith", "Frames")

    tasks = []
    wanted = []
    for stem, relative in full_layout():
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            fail("missing source frame " + relative)
            continue
        asset_name = "T_Wraith_" + stem
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
        stem = texture_name[len("T_Wraith_"):]
        sprite_name = "SPR_" + texture_name[len("T_"):]
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/" + sprite_name)
        if sprite is None:
            sprite = _asset_tools.create_asset(
                sprite_name, SPRITE_DIR, unreal.PaperSprite, factory)
        if sprite is None:
            fail("could not create sprite " + sprite_name)
            continue

        if is_projectile(stem):
            # Centre pivot on a square canvas - see the module docstring.
            size = float(ARROW_SIZE)
            pivot = unreal.Vector2D(ARROW_PIVOT, ARROW_PIVOT)
            dimension = unreal.Vector2D(size, size)
        else:
            pivot = unreal.Vector2D(PIVOT_X, PIVOT_Y)
            dimension = unreal.Vector2D(float(FRAME_WIDTH), float(FRAME_HEIGHT))

        set_prop(sprite, "source_texture", texture)
        set_prop(sprite, "source_uv", unreal.Vector2D(0.0, 0.0))
        set_prop(sprite, "source_dimension", dimension)
        set_prop(sprite, "pixels_per_unreal_unit", PIXELS_PER_UNREAL_UNIT)
        set_prop(sprite, "pivot_mode", unreal.SpritePivotMode.CUSTOM)
        set_prop(sprite, "custom_pivot_point", pivot)
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
            name = "FB_Wraith_{0}_{1}".format(anim, direction)
            fb = build(name, ["SPR_Wraith_{0}_{1}_{2:02d}".format(anim, direction, i)
                              for i in range(1, count + 1)], fps)
            if fb:
                flipbooks[name] = fb

    for direction in DIRECTIONS:
        name = "FB_Wraith_Idle_" + direction
        fb = build(name, ["SPR_Wraith_Idle_" + direction], IDLE_FPS)
        if fb:
            flipbooks[name] = fb

    death = build("FB_Wraith_Death",
                  ["SPR_Wraith_Death_{0:02d}".format(i)
                   for i in range(1, DEATH_FRAME_COUNT + 1)], DEATH_FPS)
    if death:
        flipbooks["FB_Wraith_Death"] = death

    for direction in DIRECTIONS:
        name = "FB_Wraith_Arrow_" + direction
        fb = build(name, ["SPR_Wraith_Arrow_{0}_{1:02d}".format(direction, i)
                          for i in range(1, ARROW_FRAME_COUNT + 1)], ARROW_FPS)
        if fb:
            flipbooks[name] = fb

    impact = build("FB_Wraith_Impact",
                   ["SPR_Wraith_Impact_{0:02d}".format(i)
                    for i in range(1, IMPACT_FRAME_COUNT + 1)], IMPACT_FPS)
    if impact:
        flipbooks["FB_Wraith_Impact"] = impact

    info("flipbooks ready: {0}".format(len(flipbooks)))
    return flipbooks


# ---------------------------------------------------------------------------
# 4. Blueprints
# ---------------------------------------------------------------------------
def directional(flipbooks, prefix):
    value = unreal.PTKDirectionalFlipbooks()
    for direction in DIRECTIONS:
        value.set_editor_property(direction.lower(), flipbooks.get(prefix + direction))
    return value


def create_arrow_blueprint(flipbooks):
    projectile_class = getattr(unreal, "PTKProjectile", None)
    if projectile_class is None:
        fail("APTKProjectile is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_Arrow_Wraith"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", projectile_class)
        blueprint = _asset_tools.create_asset(
            "BP_Arrow_Wraith", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_Arrow_Wraith")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Arrow_Wraith class defaults")
        return blueprint

    set_prop(cdo, "flight_flipbooks", directional(flipbooks, "FB_Wraith_Arrow_"))
    set_prop(cdo, "impact_flipbook", flipbooks.get("FB_Wraith_Impact"))
    set_prop(cdo, "impact_lifetime", IMPACT_LIFETIME)
    set_prop(cdo, "collision_radius", ARROW_COLLISION_RADIUS)
    set_prop(cdo, "splash_radius", ARROW_SPLASH_RADIUS)
    # Speed, damage and range are overwritten by Launch from the shooter's own
    # stats. They are set here so the asset reads sensibly on its own and so a
    # projectile placed by hand in a level still behaves.
    set_prop(cdo, "speed", ARROW_SPEED)
    set_prop(cdo, "damage", WRAITH_DAMAGE)
    set_prop(cdo, "max_range", WRAITH_RANGE_TILES * TILE_SIZE)

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Arrow_Wraith did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Arrow_Wraith ready")
    return blueprint


def create_blueprint(flipbooks, arrow_blueprint):
    guard_class = getattr(unreal, "PTKGuardCharacter", None)
    if guard_class is None:
        fail("APTKGuardCharacter is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_Wraith"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", guard_class)
        blueprint = _asset_tools.create_asset(
            "BP_Wraith", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_Wraith")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Wraith class defaults")
        return blueprint

    set_prop(cdo, "idle_flipbooks", directional(flipbooks, "FB_Wraith_Idle_"))
    set_prop(cdo, "walk_flipbooks", directional(flipbooks, "FB_Wraith_Walk_"))
    set_prop(cdo, "attack_flipbooks", directional(flipbooks, "FB_Wraith_Attack_"))
    set_prop(cdo, "death_flipbook", flipbooks.get("FB_Wraith_Death"))

    set_prop(cdo, "max_move_speed", WRAITH_MOVE_SPEED)
    set_prop(cdo, "attack_damage", WRAITH_DAMAGE)
    set_prop(cdo, "tile_size", TILE_SIZE)
    set_prop(cdo, "attack_range_tiles", WRAITH_RANGE_TILES)
    set_prop(cdo, "collision_radius", WRAITH_COLLISION_RADIUS)
    set_prop(cdo, "collision_half_height", WRAITH_COLLISION_HALF_HEIGHT)
    set_prop(cdo, "default_facing_direction", unreal.PTKFacingDirection.DOWN)

    # Identity, so the player health panel and the defeat banner name the guard
    # actually being played instead of whoever the HUD was first written for.
    set_prop(cdo, "guard_id", "Wraith")
    set_prop(cdo, "guard_display_name", "Wraith")

    for prop, path in (("default_mapping_context", MAPPING_CONTEXT),
                       ("move_action", MOVE_ACTION),
                       ("attack_action", ATTACK_ACTION)):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            warn("input asset missing: " + path)
            continue
        set_prop(cdo, prop, asset)

    # This one property is what makes him ranged. With it set the shared base
    # fires at the release frame instead of running the melee sphere; without
    # it he would swing his bow like a club.
    if arrow_blueprint is not None:
        set_prop(cdo, "projectile_class", arrow_blueprint.generated_class())
    set_prop(cdo, "projectile_speed", ARROW_SPEED)
    set_prop(cdo, "muzzle_forward_offset", MUZZLE_FORWARD)
    set_prop(cdo, "muzzle_height_offset", MUZZLE_HEIGHT)
    set_prop(cdo, "attack_impact_fraction", WRAITH_RELEASE_FRACTION)

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", WRAITH_MAX_HP)
    else:
        warn("could not reach BP_Wraith's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Wraith did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Wraith ready")
    return blueprint


# ---------------------------------------------------------------------------
# 5. Verification
# ---------------------------------------------------------------------------
def verify():
    info("")
    info("-" * 62)
    info("verification")
    ok = True

    character_pivots = set()
    character_dims = set()
    arrow_pivots = set()
    arrow_dims = set()
    total = 0
    for stem, _relative in full_layout():
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/SPR_Wraith_" + stem)
        if sprite is None:
            ok = False
            fail("missing sprite SPR_Wraith_" + stem)
            continue
        total += 1
        pivot = sprite.get_editor_property("custom_pivot_point")
        dimension = sprite.get_editor_property("source_dimension")
        if is_projectile(stem):
            arrow_pivots.add((round(pivot.x), round(pivot.y)))
            arrow_dims.add((round(dimension.x), round(dimension.y)))
        else:
            character_pivots.add((round(pivot.x), round(pivot.y)))
            character_dims.add((round(dimension.x), round(dimension.y)))

    if character_pivots == {(int(PIVOT_X), int(PIVOT_Y))} and \
            character_dims == {(FRAME_WIDTH, FRAME_HEIGHT)}:
        info("PASS  76 character sprites are {0}x{1} at pivot ({2}, {3})".format(
            FRAME_WIDTH, FRAME_HEIGHT, int(PIVOT_X), int(PIVOT_Y)))
    else:
        ok = False
        fail("character sprites inconsistent: pivots {0} dims {1}".format(
            character_pivots, character_dims))

    if arrow_pivots == {(int(ARROW_PIVOT), int(ARROW_PIVOT))} and \
            arrow_dims == {(ARROW_SIZE, ARROW_SIZE)}:
        info("PASS  15 projectile sprites are {0}x{0} at centre pivot ({1}, {1})".format(
            ARROW_SIZE, int(ARROW_PIVOT)))
    else:
        ok = False
        fail("projectile sprites inconsistent: pivots {0} dims {1}".format(
            arrow_pivots, arrow_dims))

    expected = [("Idle", 1, IDLE_FPS), ("Walk", WALK_FRAME_COUNT, WALK_FPS),
                ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS),
                ("Arrow", ARROW_FRAME_COUNT, ARROW_FPS)]
    for anim, count, fps in expected:
        for direction in DIRECTIONS:
            name = "FB_Wraith_{0}_{1}".format(anim, direction)
            fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
            if fb is None:
                ok = False
                fail("missing " + name)
                continue
            keys = fb.get_editor_property("key_frames")
            if len(keys) != count:
                ok = False
                fail("{0} has {1} frames, expected {2}".format(name, len(keys), count))
    for name, count in (("FB_Wraith_Death", DEATH_FRAME_COUNT),
                        ("FB_Wraith_Impact", IMPACT_FRAME_COUNT)):
        fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
        if fb is None or len(fb.get_editor_property("key_frames")) != count:
            ok = False
            fail("{0} missing or wrong length".format(name))
    if ok:
        info("PASS  18 flipbooks: 4 idle, 4 walk, 4 attack, 1 death, "
             "4 arrow, 1 impact")

    arrow_bp = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_Arrow_Wraith")
    if arrow_bp is None:
        ok = False
        fail("BP_Arrow_Wraith missing")
    else:
        arrow_cdo = unreal.get_default_object(arrow_bp.generated_class())
        flight = arrow_cdo.get_editor_property("flight_flipbooks")
        missing = [d for d in DIRECTIONS
                   if flight.get_editor_property(d.lower()) is None]
        if missing:
            ok = False
            fail("BP_Arrow_Wraith flight_flipbooks missing {0}".format(missing))
        if arrow_cdo.get_editor_property("impact_flipbook") is None:
            ok = False
            fail("BP_Arrow_Wraith has no impact flipbook")
        for prop, want in (("splash_radius", ARROW_SPLASH_RADIUS),
                           ("collision_radius", ARROW_COLLISION_RADIUS)):
            got = arrow_cdo.get_editor_property(prop)
            if abs(got - want) > 0.01:
                ok = False
                fail("BP_Arrow_Wraith {0} is {1}, expected {2}".format(prop, got, want))
        if not isinstance(arrow_cdo, unreal.PTKProjectile):
            ok = False
            fail("BP_Arrow_Wraith does not derive from APTKProjectile")
        elif not missing:
            info("PASS  BP_Arrow_Wraith is an APTKProjectile with all 4 flight "
                 "directions and an impact burst")

    blueprint = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_Wraith")
    if blueprint is None:
        ok = False
        fail("BP_Wraith missing")
    else:
        cdo = unreal.get_default_object(blueprint.generated_class())
        health = cdo.get_editor_property("health_component")
        hp = health.get_editor_property("max_health") if health else 0.0
        checks = [("attack_damage", WRAITH_DAMAGE),
                  ("max_move_speed", WRAITH_MOVE_SPEED),
                  ("attack_range_tiles", WRAITH_RANGE_TILES),
                  ("tile_size", TILE_SIZE),
                  ("attack_impact_fraction", WRAITH_RELEASE_FRACTION),
                  ("projectile_speed", ARROW_SPEED)]
        for prop, want in checks:
            got = cdo.get_editor_property(prop)
            if abs(got - want) > 0.01:
                ok = False
                fail("BP_Wraith {0} is {1}, expected {2}".format(prop, got, want))
        if abs(hp - WRAITH_MAX_HP) > 0.01:
            ok = False
            fail("BP_Wraith MaxHealth is {0}, expected {1}".format(hp, WRAITH_MAX_HP))
        for prop in ("idle_flipbooks", "walk_flipbooks", "attack_flipbooks"):
            value = cdo.get_editor_property(prop)
            missing = [d for d in DIRECTIONS
                       if value.get_editor_property(d.lower()) is None]
            if missing:
                ok = False
                fail("BP_Wraith {0} missing {1}".format(prop, missing))
        if cdo.get_editor_property("death_flipbook") is None:
            ok = False
            fail("BP_Wraith has no death flipbook")
        if cdo.get_editor_property("projectile_class") is None:
            ok = False
            fail("BP_Wraith has no projectile class - he would swing, not shoot")
        for prop in ("default_mapping_context", "move_action", "attack_action"):
            if cdo.get_editor_property(prop) is None:
                ok = False
                fail("BP_Wraith has no {0} - WASD would not reach him".format(prop))
        if str(cdo.get_editor_property("guard_id")) != "Wraith":
            ok = False
            fail("BP_Wraith guard_id is {0}, expected Wraith".format(
                cdo.get_editor_property("guard_id")))
        if ok:
            info("PASS  BP_Wraith: {0:.0f} HP, {1:.0f} damage, {2} tiles ({3:.0f} uu), "
                 "speed {4:.0f}".format(hp, WRAITH_DAMAGE, WRAITH_RANGE_TILES,
                                        WRAITH_RANGE_TILES * TILE_SIZE, WRAITH_MOVE_SPEED))
            info("PASS  BP_Wraith fires BP_Arrow_Wraith at {0:.0f} uu/s, released at "
                 "{1:.3f} of the attack (frame 6 of 8)".format(
                     ARROW_SPEED, WRAITH_RELEASE_FRACTION))
            info("PASS  arrow deals {0:.0f} to a SINGLE target (splash radius 0), "
                 "sweep radius {1:.0f}".format(WRAITH_DAMAGE, ARROW_COLLISION_RADIUS))
            info("PASS  BP_Wraith carries IMC_PTK_Default, IA_Move and IA_Attack, "
                 "so WASD and the attack key reach him when possessed")
            # The point of the whole phase: Wraith IS a guard, not a parallel
            # implementation. Proven by type, not by the asset's metadata.
            if isinstance(cdo, unreal.PTKGuardCharacter):
                info("PASS  BP_Wraith is an APTKGuardCharacter - same class as Ravager "
                     "and Aegis, so health, facing, input, attack timing, death and "
                     "enemy targeting are inherited")
            else:
                ok = False
                fail("BP_Wraith does not derive from APTKGuardCharacter")

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("Wraith generation")
    info("=" * 62)

    textures = import_textures()
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    arrow = create_arrow_blueprint(flipbooks)
    create_blueprint(flipbooks, arrow)
    verify()

    info("=" * 62)
    for key in ("textures", "sprites", "flipbooks", "blueprint"):
        info("{0:<10}: {1}".format(key, _summary[key]))
    info("{0:<10}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<10}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
