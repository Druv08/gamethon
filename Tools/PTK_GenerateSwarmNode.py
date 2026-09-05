"""
Protect the King - 2D
Unreal Editor Python script: imports Swarm Node and wires up the combat test.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateSwarmNode.py"

What it creates
---------------
  Textures    T_SwarmNode_*        64 textures, point-filtered, uncompressed
  Sprites     SPR_SwarmNode_*      64 sprites, pivot (96,179), PPU 1.0
  Flipbooks   FB_SwarmNode_Idle_*   4 flipbooks, 1 frame  @  8 FPS
              FB_SwarmNode_Walk_*   4 flipbooks, 8 frames @ 10 FPS
              FB_SwarmNode_Attack_* 4 flipbooks, 8 frames @ 12 FPS
  Blueprint   BP_SwarmNode         parented to APTKEnemyCharacter
  Level       adds one Swarm Node to L_PTK_TestGround
  Tuning      applies the prototype combat values to BOTH characters

Re-running is safe: assets are updated in place and the arena is not rebuilt.

NO IDLE ART WAS SUPPLIED
------------------------
The four delivered sheets are walk and attack only. Rather than invent a rest
pose, each FB_SwarmNode_Idle_<Dir> holds a SINGLE frame - walk frame 01 of that
direction, which is the cycle's contact pose and reads as a settled stance.
That is reuse of delivered art, not fabrication of new art.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Contract - matches Tools/ExtractSwarmNodeAnimations.py and Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
FRAME_WIDTH = 192
FRAME_HEIGHT = 192
PIVOT_X = 96.0
PIVOT_Y = 179.0
PIXELS_PER_UNREAL_UNIT = 1.0

IDLE_FPS = 8.0
WALK_FPS = 10.0
ATTACK_FPS = 12.0

# 8 frames over ~0.9 s: slow enough to read as a collapse rather than a pop.
DEATH_FPS = 9.0

DIRECTIONS = ["Down", "Up", "Left", "Right"]
WALK_FRAME_COUNT = 8
ATTACK_FRAME_COUNT = 8

# ---------------------------------------------------------------------------
# Prototype balance. TEMPORARY values - every one of these is an editable
# UPROPERTY, so tuning never needs a recompile.
# ---------------------------------------------------------------------------
# Guards are built to hold a line against a crowd; a single enemy is not meant
# to threaten one. Enemy damage is deliberately UNCHANGED - the durability gap
# is the point, and inflating enemy damage to compensate would erase it.
RAVAGER_MAX_HP = 7000.0
RAVAGER_DAMAGE = 25.0

SWARM_MAX_HP = 100.0
SWARM_DAMAGE = 15.0
SWARM_MOVE_SPEED = 180.0        # Ravager is 240, so the player can disengage
SWARM_DETECTION_RANGE = 800.0
SWARM_ATTACK_COOLDOWN = 1.2

# Reach is stated in TILES, not world units, so it survives a change of map
# scale. One project-wide tile is 64 uu.
TILE_SIZE = 64.0
RAVAGER_RANGE_TILES = 3.5
SWARM_RANGE_TILES = 1.0

# Ravager's capsule is r=14, Swarm Node's r=18. Sized so the creature reads as
# beside the knight rather than standing inside him.
SWARM_COLLISION_RADIUS = 18.0
SWARM_COLLISION_HALF_HEIGHT = 18.0

# Where the creature starts, in the XZ play plane. Far enough from PlayerStart
# (the origin) that Idle -> Chase -> Attack can all be observed in order.
SWARM_SPAWN = (420.0, 0.0, -260.0)

# Development stress test. One number: 1, 5, 10 and 20 all work unchanged.
SWARM_SPAWN_COUNT = 10

SWARM_ROOT = "/Game/PTK/Characters/Enemies/SwarmNode"
TEXTURE_DIR = SWARM_ROOT + "/Textures"
SPRITE_DIR = SWARM_ROOT + "/Sprites"
FLIPBOOK_DIR = SWARM_ROOT + "/Flipbooks"
BLUEPRINT_DIR = SWARM_ROOT + "/Blueprints"

RAVAGER_BP = "/Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager"
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


DEATH_FRAME_COUNT = 8

# Death frames are 16 px taller than everything else: a corpse settles below the
# line its feet stood on. The pivot is unchanged, so the character still lands
# on the actor origin - only the canvas grew downward.
DEATH_WIDTH = 192
DEATH_HEIGHT = 208


def frame_layout():
    """(filename, relative path, (w, h)) for all 72 delivered frames."""
    layout = []
    for anim, count in (("Walk", WALK_FRAME_COUNT), ("Attack", ATTACK_FRAME_COUNT)):
        for direction in DIRECTIONS:
            for index in range(1, count + 1):
                name = "{0}_{1}_{2:02d}.png".format(anim, direction, index)
                layout.append((name, os.path.join(anim, direction, name),
                               (FRAME_WIDTH, FRAME_HEIGHT)))
    for index in range(1, DEATH_FRAME_COUNT + 1):
        name = "Death_{0:02d}.png".format(index)
        layout.append((name, os.path.join("Death", name), (DEATH_WIDTH, DEATH_HEIGHT)))
    return layout


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures():
    ensure_directory(TEXTURE_DIR)
    root = os.path.join(project_dir(), "ArtSource", "Characters", "Enemies",
                        "SwarmNode", "Frames")

    tasks = []
    wanted = []
    for name, relative, _size in frame_layout():
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            fail("missing source frame " + relative)
            continue
        asset_name = "T_SwarmNode_" + os.path.splitext(name)[0]
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

        # Pixel-art import rules, identical to Ravager's. Anything else here
        # produces a blurred or colour-bled sprite.
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

    # Death frames use a taller canvas, so the source rectangle is looked up per
    # frame instead of assumed. Using one global size here would crop them.
    sizes = {"T_SwarmNode_" + os.path.splitext(n)[0]: sz
             for n, _r, sz in frame_layout()}

    for texture_name, texture in sorted(textures.items()):
        sprite_name = "SPR_" + texture_name[len("T_"):]
        width, height = sizes.get(texture_name, (FRAME_WIDTH, FRAME_HEIGHT))
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
                 unreal.Vector2D(float(width), float(height)))
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
            name = "FB_SwarmNode_{0}_{1}".format(anim, direction)
            flipbook = build(name, [
                "SPR_SwarmNode_{0}_{1}_{2:02d}".format(anim, direction, i)
                for i in range(1, count + 1)], fps)
            if flipbook:
                flipbooks[name] = flipbook

    # Idle: walk frame 01 held as a single frame. No idle art was delivered and
    # none is being invented - this is the contact pose of the supplied cycle.
    for direction in DIRECTIONS:
        name = "FB_SwarmNode_Idle_" + direction
        flipbook = build(name, ["SPR_SwarmNode_Walk_{0}_01".format(direction)], IDLE_FPS)
        if flipbook:
            flipbooks[name] = flipbook

    # Death: one non-directional collapse. A creature falls the same way
    # whichever way it was facing.
    death = build("FB_SwarmNode_Death",
                  ["SPR_SwarmNode_Death_{0:02d}".format(i)
                   for i in range(1, DEATH_FRAME_COUNT + 1)], DEATH_FPS)
    if death:
        flipbooks["FB_SwarmNode_Death"] = death

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


RAVAGER_ROOT = "/Game/PTK/Characters/Guards/Ravager"


def import_ravager_death():
    """
    Imports Ravager's 8 death frames and builds FB_Ravager_Death.

    Lives here rather than in PTK_GenerateAssets.py because the death art was
    delivered with this combat phase, and re-running the Ravager generator would
    otherwise have to be kept in lockstep with it.
    """
    texture_dir = RAVAGER_ROOT + "/Textures"
    sprite_dir = RAVAGER_ROOT + "/Sprites"
    flipbook_dir = RAVAGER_ROOT + "/Flipbooks"
    for d in (texture_dir, sprite_dir, flipbook_dir):
        ensure_directory(d)

    root = os.path.join(project_dir(), "ArtSource", "Characters", "Guards",
                        "Ravager", "Frames", "Death")

    tasks = []
    names = []
    for index in range(1, DEATH_FRAME_COUNT + 1):
        filename = "Death_{0:02d}.png".format(index)
        full = os.path.join(root, filename)
        if not os.path.isfile(full):
            fail("missing Ravager death frame " + filename)
            continue
        asset_name = "T_Ravager_Death_{0:02d}".format(index)
        names.append(asset_name)

        task = unreal.AssetImportTask()
        task.set_editor_property("filename", full)
        task.set_editor_property("destination_path", texture_dir)
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        tasks.append(task)

    if tasks:
        _asset_tools.import_asset_tasks(tasks)

    sprite_factory = unreal.PaperSpriteFactory()
    sprite_names = []
    for asset_name in names:
        texture = unreal.EditorAssetLibrary.load_asset(texture_dir + "/" + asset_name)
        if texture is None:
            fail("Ravager death texture failed to import: " + asset_name)
            continue
        set_prop(texture, "filter", unreal.TextureFilter.TF_NEAREST)
        set_prop(texture, "mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        set_prop(texture, "compression_settings",
                 unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        set_prop(texture, "srgb", True)
        set_prop(texture, "never_stream", True)
        set_prop(texture, "lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
        _summary["textures"] += 1

        sprite_name = "SPR_" + asset_name[len("T_"):]
        sprite = unreal.EditorAssetLibrary.load_asset(sprite_dir + "/" + sprite_name)
        if sprite is None:
            sprite = _asset_tools.create_asset(
                sprite_name, sprite_dir, unreal.PaperSprite, sprite_factory)
        if sprite is None:
            fail("could not create " + sprite_name)
            continue
        set_prop(sprite, "source_texture", texture)
        set_prop(sprite, "source_uv", unreal.Vector2D(0.0, 0.0))
        set_prop(sprite, "source_dimension",
                 unreal.Vector2D(float(DEATH_WIDTH), float(DEATH_HEIGHT)))
        set_prop(sprite, "pixels_per_unreal_unit", PIXELS_PER_UNREAL_UNIT)
        set_prop(sprite, "pivot_mode", unreal.SpritePivotMode.CUSTOM)
        set_prop(sprite, "custom_pivot_point", unreal.Vector2D(PIVOT_X, PIVOT_Y))
        set_prop(sprite, "snap_pivot_to_pixel_grid", True)
        set_prop(sprite, "sprite_collision_domain", unreal.SpriteCollisionMode.NONE)
        unreal.EditorAssetLibrary.save_loaded_asset(sprite, only_if_is_dirty=False)
        sprite_names.append(sprite_name)
        _summary["sprites"] += 1

    frames = []
    for sprite_name in sprite_names:
        sprite = unreal.EditorAssetLibrary.load_asset(sprite_dir + "/" + sprite_name)
        key = unreal.PaperFlipbookKeyFrame()
        key.set_editor_property("sprite", sprite)
        key.set_editor_property("frame_run", 1)
        frames.append(key)

    name = "FB_Ravager_Death"
    flipbook = unreal.EditorAssetLibrary.load_asset(flipbook_dir + "/" + name)
    if flipbook is None:
        flipbook = _asset_tools.create_asset(
            name, flipbook_dir, unreal.PaperFlipbook, unreal.PaperFlipbookFactory())
    if flipbook is None:
        fail("could not create FB_Ravager_Death")
        return None
    set_prop(flipbook, "frames_per_second", DEATH_FPS)
    set_prop(flipbook, "key_frames", frames)
    unreal.EditorAssetLibrary.save_loaded_asset(flipbook, only_if_is_dirty=False)
    _summary["flipbooks"] += 1
    info("Ravager death animation ready ({0} frames @ {1} FPS)".format(len(frames), DEATH_FPS))
    return flipbook


def create_swarm_blueprint(flipbooks):
    enemy_class = getattr(unreal, "PTKEnemyCharacter", None)
    if enemy_class is None:
        fail("APTKEnemyCharacter is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_SwarmNode"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", enemy_class)
        blueprint = _asset_tools.create_asset(
            "BP_SwarmNode", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_SwarmNode")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_SwarmNode class defaults")
        return blueprint

    set_prop(cdo, "idle_flipbooks", directional(flipbooks, "FB_SwarmNode_Idle_"))
    set_prop(cdo, "walk_flipbooks", directional(flipbooks, "FB_SwarmNode_Walk_"))
    set_prop(cdo, "attack_flipbooks", directional(flipbooks, "FB_SwarmNode_Attack_"))

    set_prop(cdo, "enemy_id", "SwarmNode")
    set_prop(cdo, "enemy_display_name", unreal.Text("Swarm Node"))

    set_prop(cdo, "max_move_speed", SWARM_MOVE_SPEED)
    set_prop(cdo, "collision_radius", SWARM_COLLISION_RADIUS)
    set_prop(cdo, "collision_half_height", SWARM_COLLISION_HALF_HEIGHT)
    set_prop(cdo, "default_facing_direction", unreal.PTKFacingDirection.DOWN)

    set_prop(cdo, "detection_range", SWARM_DETECTION_RANGE)
    set_prop(cdo, "attack_cooldown", SWARM_ATTACK_COOLDOWN)
    set_prop(cdo, "attack_damage", SWARM_DAMAGE)
    set_prop(cdo, "tile_size", TILE_SIZE)
    set_prop(cdo, "attack_range_tiles", SWARM_RANGE_TILES)
    set_prop(cdo, "death_flipbook", flipbooks.get("FB_SwarmNode_Death"))

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", SWARM_MAX_HP)
    else:
        warn("could not reach BP_SwarmNode's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_SwarmNode did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_SwarmNode ready")
    return blueprint


def tune_ravager(death_flipbook):
    """Applies the prototype combat values to the existing Ravager Blueprint."""
    blueprint = unreal.EditorAssetLibrary.load_asset(RAVAGER_BP)
    if blueprint is None:
        fail("BP_Ravager not found - run Tools/PTK_GenerateAssets.py first")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach BP_Ravager class defaults")
        return None

    set_prop(cdo, "attack_damage", RAVAGER_DAMAGE)
    set_prop(cdo, "tile_size", TILE_SIZE)
    set_prop(cdo, "attack_range_tiles", RAVAGER_RANGE_TILES)
    if death_flipbook:
        set_prop(cdo, "death_flipbook", death_flipbook)

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", RAVAGER_MAX_HP)
    else:
        warn("could not reach BP_Ravager's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Ravager did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    info("BP_Ravager tuned: {0} HP, {1} damage, reach {2} tiles ({3:.0f} uu)".format(
        RAVAGER_MAX_HP, RAVAGER_DAMAGE, RAVAGER_RANGE_TILES, RAVAGER_RANGE_TILES * TILE_SIZE))
    return blueprint


# ---------------------------------------------------------------------------
# 5. Place one Swarm Node in the arena
# ---------------------------------------------------------------------------
def place_in_level(blueprint):
    """
    Replaces the single hand-placed Swarm Node with a development spawner.

    The spawner is what makes 1 / 5 / 10 / 20 a one-number change; leaving a
    hand-placed enemy in as well would silently add one to every count.
    """
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if level_subsystem is None or actor_subsystem is None:
        fail("editor subsystems unavailable - cannot place the spawner")
        return False

    spawner_class = getattr(unreal, "PTKEnemySpawner", None)
    if spawner_class is None:
        fail("APTKEnemySpawner is not loaded - compile the C++ module first")
        return False

    level_subsystem.load_level(LEVEL_PATH)

    # Re-running must not stack duplicates, and the old single enemy from the
    # 1v1 phase has to go or every stress test would be off by one.
    for actor in actor_subsystem.get_all_level_actors():
        if not actor:
            continue
        label = actor.get_actor_label()
        if label.startswith("SwarmNode") or label.startswith("SwarmSpawner"):
            actor_subsystem.destroy_actor(actor)

    spawner = actor_subsystem.spawn_actor_from_class(
        spawner_class, unreal.Vector(*SWARM_SPAWN), unreal.Rotator(0.0, 0.0, 0.0))
    if spawner is None:
        fail("could not spawn APTKEnemySpawner into the level")
        return False

    spawner.set_actor_label("SwarmSpawner")
    set_prop(spawner, "enemy_class", blueprint.generated_class())
    set_prop(spawner, "spawn_count", SWARM_SPAWN_COUNT)

    level_subsystem.save_current_level()
    info("SwarmSpawner placed at {0}, SpawnCount = {1}".format(
        SWARM_SPAWN, SWARM_SPAWN_COUNT))
    return True


# ---------------------------------------------------------------------------
# 6. Verification
# ---------------------------------------------------------------------------
def verify():
    info("-" * 62)
    info("VERIFICATION")
    info("-" * 62)
    ok = True

    pivots = set()
    dims = set()
    missing = []
    for name, _relative, size in frame_layout():
        sprite_name = "SPR_SwarmNode_" + os.path.splitext(name)[0]
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/" + sprite_name)
        if sprite is None:
            missing.append(sprite_name)
            continue
        pivot = sprite.get_editor_property("custom_pivot_point")
        pivots.add((round(pivot.x, 3), round(pivot.y, 3)))
        dimension = sprite.get_editor_property("source_dimension")
        if (round(dimension.x), round(dimension.y)) != size:
            dims.add(((round(dimension.x), round(dimension.y)), size))

    if missing:
        ok = False
        fail("missing sprites: " + ", ".join(missing[:5]))
    elif pivots == {(PIVOT_X, PIVOT_Y)}:
        info("PASS  72/72 sprites share the pivot ({0}, {1})".format(PIVOT_X, PIVOT_Y))
    else:
        ok = False
        fail("sprites disagree about the pivot: {0}".format(pivots))

    if not dims:
        info("PASS  72/72 sprites match their expected size "
             "({0}x{1}, death {2}x{3})".format(FRAME_WIDTH, FRAME_HEIGHT,
                                               DEATH_WIDTH, DEATH_HEIGHT))
    else:
        ok = False
        fail("sprite dimension mismatches (actual, expected): {0}".format(dims))

    death_fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/FB_SwarmNode_Death")
    if death_fb is None:
        ok = False
        fail("missing FB_SwarmNode_Death")
    elif len(death_fb.get_editor_property("key_frames")) != DEATH_FRAME_COUNT:
        ok = False
        fail("FB_SwarmNode_Death has {0} frames, expected {1}".format(
            len(death_fb.get_editor_property("key_frames")), DEATH_FRAME_COUNT))

    for anim, count, fps in (("Idle", 1, IDLE_FPS),
                             ("Walk", WALK_FRAME_COUNT, WALK_FPS),
                             ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS)):
        for direction in DIRECTIONS:
            name = "FB_SwarmNode_{0}_{1}".format(anim, direction)
            flipbook = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
            if flipbook is None:
                ok = False
                fail("missing flipbook " + name)
                continue
            frames = flipbook.get_editor_property("key_frames")
            if len(frames) != count:
                ok = False
                fail("{0} has {1} frames, expected {2}".format(name, len(frames), count))
            actual_fps = flipbook.get_editor_property("frames_per_second")
            if abs(actual_fps - fps) > 0.001:
                ok = False
                fail("{0} runs at {1} FPS, expected {2}".format(name, actual_fps, fps))
            for index, frame in enumerate(frames):
                sprite = frame.get_editor_property("sprite")
                if sprite is None:
                    ok = False
                    fail(name + " has an empty key frame")
                    continue
                expected = ("SPR_SwarmNode_Walk_{0}_01".format(direction) if anim == "Idle"
                            else "SPR_SwarmNode_{0}_{1}_{2:02d}".format(anim, direction, index + 1))
                if sprite.get_name() != expected:
                    ok = False
                    fail("{0}[{1}] = {2}, expected {3}".format(
                        name, index, sprite.get_name(), expected))

    if ok:
        info("PASS  12/12 flipbooks: 4 idle (1 frame), 4 walk (8 @ {0}), "
             "4 attack (8 @ {1})".format(WALK_FPS, ATTACK_FPS))

    blueprint = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_SwarmNode")
    if blueprint is None:
        ok = False
        fail("BP_SwarmNode missing")
    else:
        cdo = unreal.get_default_object(blueprint.generated_class())
        checks = [
            ("max_move_speed", SWARM_MOVE_SPEED),
            ("detection_range", SWARM_DETECTION_RANGE),
            ("attack_range_tiles", SWARM_RANGE_TILES),
            ("tile_size", TILE_SIZE),
            ("attack_damage", SWARM_DAMAGE),
            ("attack_cooldown", SWARM_ATTACK_COOLDOWN),
        ]
        for prop, expected in checks:
            actual = cdo.get_editor_property(prop)
            if abs(actual - expected) > 0.001:
                ok = False
                fail("BP_SwarmNode.{0} = {1}, expected {2}".format(prop, actual, expected))
        health = cdo.get_editor_property("health_component")
        if health and abs(health.get_editor_property("max_health") - SWARM_MAX_HP) > 0.001:
            ok = False
            fail("BP_SwarmNode MaxHealth = {0}, expected {1}".format(
                health.get_editor_property("max_health"), SWARM_MAX_HP))
        for slot in ("idle_flipbooks", "walk_flipbooks", "attack_flipbooks"):
            value = cdo.get_editor_property(slot)
            for direction in DIRECTIONS:
                if value.get_editor_property(direction.lower()) is None:
                    ok = False
                    fail("BP_SwarmNode.{0}.{1} is empty".format(slot, direction))
        if cdo.get_editor_property("death_flipbook") is None:
            ok = False
            fail("BP_SwarmNode has no death flipbook assigned")
        if ok:
            info("PASS  BP_SwarmNode: {0} HP, {1} damage, speed {2}, detect {3}, "
                 "reach {4} tiles ({5:.0f} uu), cooldown {6}".format(
                     SWARM_MAX_HP, SWARM_DAMAGE, SWARM_MOVE_SPEED,
                     SWARM_DETECTION_RANGE, SWARM_RANGE_TILES,
                     SWARM_RANGE_TILES * TILE_SIZE, SWARM_ATTACK_COOLDOWN))

    ravager = unreal.EditorAssetLibrary.load_asset(RAVAGER_BP)
    if ravager:
        cdo = unreal.get_default_object(ravager.generated_class())
        health = cdo.get_editor_property("health_component")
        damage = cdo.get_editor_property("attack_damage")
        hp = health.get_editor_property("max_health") if health else -1
        if abs(damage - RAVAGER_DAMAGE) > 0.001 or abs(hp - RAVAGER_MAX_HP) > 0.001:
            ok = False
            fail("BP_Ravager: HP {0} damage {1}, expected {2}/{3}".format(
                hp, damage, RAVAGER_MAX_HP, RAVAGER_DAMAGE))
        elif cdo.get_editor_property("death_flipbook") is None:
            ok = False
            fail("BP_Ravager has no death flipbook assigned")
        else:
            reach = cdo.get_editor_property("attack_range_tiles")
            info("PASS  BP_Ravager: {0} HP, {1} damage, reach {2} tiles ({3:.0f} uu)"
                 .format(hp, damage, reach, reach * TILE_SIZE))
            info("PASS  range advantage: guard {0} vs enemy {1} tiles = +{2} tiles "
                 "({3:.0f} uu)".format(RAVAGER_RANGE_TILES, SWARM_RANGE_TILES,
                                       RAVAGER_RANGE_TILES - SWARM_RANGE_TILES,
                                       (RAVAGER_RANGE_TILES - SWARM_RANGE_TILES) * TILE_SIZE))

    info("-" * 62)
    info("VERIFICATION: " + ("ALL CHECKS PASSED" if ok else "FAILURES ABOVE"))
    info("-" * 62)
    return ok


def main():
    info("=" * 62)
    info("Swarm Node generation")
    info("=" * 62)

    textures = import_textures()
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    blueprint = create_swarm_blueprint(flipbooks)
    ravager_death = import_ravager_death()
    tune_ravager(ravager_death)
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
