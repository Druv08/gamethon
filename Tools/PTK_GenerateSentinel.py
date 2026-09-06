"""
Protect the King - 2D
Unreal Editor Python script: imports Sentinel and wires up the mage guard.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateSentinel.py"

What it creates
---------------
  Textures    T_Sentinel_*       91 textures, point-filtered, uncompressed
  Sprites     SPR_Sentinel_*     91 sprites
                                 76 character, 192x208, pivot (96,179)
                                 15 projectile, 129x129, pivot (64,64)
  Flipbooks   FB_Sentinel_Idle_*    4 flipbooks, 1 frame  @  8 FPS
              FB_Sentinel_Walk_*    4 flipbooks, 8 frames @ 10 FPS
              FB_Sentinel_Attack_*  4 flipbooks, 8 frames @ 12 FPS
              FB_Sentinel_Death     1 flipbook,  8 frames @  9 FPS
              FB_Sentinel_Orb_*     4 flipbooks, 3 frames @ 12 FPS
              FB_Sentinel_Impact    1 flipbook,  3 frames @ 12 FPS
  Blueprints  BP_Orb_Sentinel     parented to APTKProjectile
              BP_Sentinel         parented to APTKGuardCharacter

Re-running is safe: assets are updated in place, and nothing about Ravager,
Aegis, Reaver, Wraith, Swarm Node, the King or the level is touched.


SENTINEL ADDS NO SYSTEM AT ALL
------------------------------
BP_Sentinel derives from APTKGuardCharacter, the same class every other guard
uses, and fires through APTKProjectile - the ranged path built for Wraith. There
is no second projectile architecture: he sets ProjectileClass to his own orb
Blueprint and everything else is inherited.

So he reuses, rather than re-implements: the shared UPTKHealthComponent, facing,
the Idle/Walk/Attack/Dead machine, release-frame timing and its facing lock, the
projectile's flight sweep, hostility rules, impact and expiry, player input,
death handling, and being recognised as a guard by enemy targeting and the King
fallback.

The ONE behaviour that is new is single-target magic, and even that is a value
rather than code: his orb's SplashRadius is 0, which APTKProjectile already
understood to mean "damage only what was struck". Wraith's arrow keeps its
blast; Sentinel's spell hits one enemy.


THE ORB PIVOT IS THE CENTRE, NOT THE FEET
-----------------------------------------
Every character sprite in this project pivots on the feet, because that is what
makes a character stand on a point. A projectile has no feet: it pivots on its
own centre, so the actor location IS the orb, which is what makes the flight
sweep, the impact position and the drawn sprite agree with one another.

The orb canvas is 129x129 - odd, so there is a true centre pixel at (64,64).
That is what lets the four directions be exact 90-degree rotations of one
drawing rather than a runtime rotation of a sprite, which would resample pixel
art. The rotations are baked by Tools/ExtractSentinelAnimations.py.


HIS CHARACTER CANVAS IS 192x208, NOT 192x192
--------------------------------------------
16 px taller at the bottom, same pivot, so his feet still land on the actor
origin exactly like every other guard. He fits 192x192 only by a single pixel
below - his death collapse reaches 11 px under the feet row against the 12 that
canvas leaves - and one pixel is not a margin. See his extractor.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Contract - matches Tools/ExtractSentinelAnimations.py and Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
FRAME_WIDTH = 224
FRAME_HEIGHT = 224
PIVOT_X = 112.0
PIVOT_Y = 200.0
PIXELS_PER_UNREAL_UNIT = 1.0

ORB_SIZE = 129
ORB_PIVOT = 64.0

IDLE_FPS = 8.0
WALK_FPS = 10.0
ATTACK_FPS = 12.0
DEATH_FPS = 9.0
ORB_FPS = 12.0
IMPACT_FPS = 12.0

DIRECTIONS = ["Down", "Up", "Left", "Right"]
WALK_FRAME_COUNT = 8
ATTACK_FRAME_COUNT = 8
DEATH_FRAME_COUNT = 8
ORB_FRAME_COUNT = 3
IMPACT_FRAME_COUNT = 3

# ---------------------------------------------------------------------------
# Prototype balance - Sentinel is the ranged skirmisher
# ---------------------------------------------------------------------------
# Ravager: 7000 HP, 25 damage, 240 uu/s, 3.5 tiles - the bruiser.
# Aegis:   9000 HP, 20 damage, 200 uu/s, 3.5 tiles - the tank.
# Reaver:  5500 HP, 35 damage, 300 uu/s, 3.5 tiles - the assassin.
# Wraith:  5000 HP, 30 damage, 270 uu/s, 7.0 tiles - the archer.
# Sentinel:6000 HP, 40 damage, 230 uu/s, 6.0 tiles - the mage. The hardest
#          single hit in the game, and the slowest guard but one, at a range
#          just short of the archer's.
SENTINEL_MAX_HP = 6000.0
SENTINEL_DAMAGE = 40.0
SENTINEL_MOVE_SPEED = 230.0
TILE_SIZE = 64.0
SENTINEL_RANGE_TILES = 6.0

SENTINEL_COLLISION_RADIUS = 14.0
SENTINEL_COLLISION_HALF_HEIGHT = 14.0

# The orb leaves the staff on frame 5 of 8, which begins at 4/8 - read off the
# artwork, where frame 4 still holds the charged disc at the staff head and
# frame 5 is the first with the orb detached and streaking away. That streak is
# also independent proof of the Left/Right mapping: it travels screen-left on
# row0 and screen-right on row1.
SENTINEL_RELEASE_FRACTION = 0.5

# 700 uu/s crosses his 6 tiles in just over half a second. Slower than Wraith's
# 900: a heavy magic orb should not read as a bullet, and the extra travel time
# is what makes his longer wind-up feel like the trade for the bigger hit.
ORB_SPEED = 700.0

# A little wider than the arrow's 12 - an orb is a fatter thing than a shaft.
ORB_COLLISION_RADIUS = 14.0

# 96 uu = 1.5 tiles. He is a mage: the spell bursts, and every living enemy
# inside takes the full 40 exactly once - the direct target included, since it
# stands at the centre of its own blast. APTKProjectile tracks who it has
# already struck, so being both the direct hit and inside the sphere cannot
# damage anything twice.
ORB_SPLASH_RADIUS = 1.5 * TILE_SIZE

# Measured off the finished attack frames, where the released spell's energy
# centroid sits 92-127 px above the feet (his floating orbs pull that upward, so
# the staff head itself is nearer 100) and within 17 px of his centre.
#
# MUZZLE_HEIGHT is VISUAL ONLY - it lifts the orb's sprite to the staff head but
# leaves the actor on the combat row. See APTKProjectile: a projectile that
# FLEW at staff height could not hit anything standing level with the caster.
MUZZLE_FORWARD = 26.0

# 70, NOT the ~100 of his staff head, and this is a gameplay decision rather
# than an art one.
#
# A Swarm Node is drawn only 92 px tall above its feet row. An orb lifted 100 px
# is therefore drawn ABOVE the top of every enemy in the game: it sailed over
# their heads and the burst appeared at their feet, which read as the spell
# passing through them without connecting. The collision was never wrong - it
# stopped on the first enemy every time - but nothing on screen said so.
#
# 70 puts the orb three quarters up an enemy's body, so it visibly crosses what
# it hits. It is the same value Wraith's arrow uses, for the same reason. The
# cost is that the orb leaves nearer the mage's chest than his staff head.
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

SENTINEL_ROOT = "/Game/PTK/Characters/Guards/Sentinel"
TEXTURE_DIR = SENTINEL_ROOT + "/Textures"
SPRITE_DIR = SENTINEL_ROOT + "/Sprites"
FLIPBOOK_DIR = SENTINEL_ROOT + "/Flipbooks"
BLUEPRINT_DIR = SENTINEL_ROOT + "/Blueprints"

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
        for index in range(1, ORB_FRAME_COUNT + 1):
            name = "Orb_{0}_{1:02d}".format(direction, index)
            layout.append((name, os.path.join("Orb", direction, name + ".png")))
    for index in range(1, IMPACT_FRAME_COUNT + 1):
        name = "Impact_{0:02d}".format(index)
        layout.append((name, os.path.join("Impact", name + ".png")))
    return layout


def full_layout():
    return character_layout() + projectile_layout()


def is_projectile(stem):
    return stem.startswith("Orb_") or stem.startswith("Impact_")


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures():
    ensure_directory(TEXTURE_DIR)
    root = os.path.join(project_dir(), "ArtSource", "Characters", "Guards",
                        "Sentinel", "Frames")

    tasks = []
    wanted = []
    for stem, relative in full_layout():
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            fail("missing source frame " + relative)
            continue
        asset_name = "T_Sentinel_" + stem
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
        stem = texture_name[len("T_Sentinel_"):]
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
            size = float(ORB_SIZE)
            pivot = unreal.Vector2D(ORB_PIVOT, ORB_PIVOT)
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
            name = "FB_Sentinel_{0}_{1}".format(anim, direction)
            fb = build(name, ["SPR_Sentinel_{0}_{1}_{2:02d}".format(anim, direction, i)
                              for i in range(1, count + 1)], fps)
            if fb:
                flipbooks[name] = fb

    for direction in DIRECTIONS:
        name = "FB_Sentinel_Idle_" + direction
        fb = build(name, ["SPR_Sentinel_Idle_" + direction], IDLE_FPS)
        if fb:
            flipbooks[name] = fb

    death = build("FB_Sentinel_Death",
                  ["SPR_Sentinel_Death_{0:02d}".format(i)
                   for i in range(1, DEATH_FRAME_COUNT + 1)], DEATH_FPS)
    if death:
        flipbooks["FB_Sentinel_Death"] = death

    for direction in DIRECTIONS:
        name = "FB_Sentinel_Orb_" + direction
        fb = build(name, ["SPR_Sentinel_Orb_{0}_{1:02d}".format(direction, i)
                          for i in range(1, ORB_FRAME_COUNT + 1)], ORB_FPS)
        if fb:
            flipbooks[name] = fb

    impact = build("FB_Sentinel_Impact",
                   ["SPR_Sentinel_Impact_{0:02d}".format(i)
                    for i in range(1, IMPACT_FRAME_COUNT + 1)], IMPACT_FPS)
    if impact:
        flipbooks["FB_Sentinel_Impact"] = impact

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


def create_orb_blueprint(flipbooks):
    projectile_class = getattr(unreal, "PTKProjectile", None)
    if projectile_class is None:
        fail("APTKProjectile is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_Orb_Sentinel"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", projectile_class)
        blueprint = _asset_tools.create_asset(
            "BP_Orb_Sentinel", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_Orb_Sentinel")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Orb_Sentinel class defaults")
        return blueprint

    set_prop(cdo, "flight_flipbooks", directional(flipbooks, "FB_Sentinel_Orb_"))
    set_prop(cdo, "impact_flipbook", flipbooks.get("FB_Sentinel_Impact"))
    set_prop(cdo, "impact_lifetime", IMPACT_LIFETIME)
    set_prop(cdo, "collision_radius", ORB_COLLISION_RADIUS)
    set_prop(cdo, "splash_radius", ORB_SPLASH_RADIUS)
    # Speed, damage and range are overwritten by Launch from the shooter's own
    # stats. They are set here so the asset reads sensibly on its own and so a
    # projectile placed by hand in a level still behaves.
    set_prop(cdo, "speed", ORB_SPEED)
    set_prop(cdo, "damage", SENTINEL_DAMAGE)
    set_prop(cdo, "max_range", SENTINEL_RANGE_TILES * TILE_SIZE)

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Orb_Sentinel did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Orb_Sentinel ready")
    return blueprint


def create_blueprint(flipbooks, orb_blueprint):
    guard_class = getattr(unreal, "PTKGuardCharacter", None)
    if guard_class is None:
        fail("APTKGuardCharacter is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_Sentinel"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", guard_class)
        blueprint = _asset_tools.create_asset(
            "BP_Sentinel", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_Sentinel")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Sentinel class defaults")
        return blueprint

    set_prop(cdo, "idle_flipbooks", directional(flipbooks, "FB_Sentinel_Idle_"))
    set_prop(cdo, "walk_flipbooks", directional(flipbooks, "FB_Sentinel_Walk_"))
    set_prop(cdo, "attack_flipbooks", directional(flipbooks, "FB_Sentinel_Attack_"))
    set_prop(cdo, "death_flipbook", flipbooks.get("FB_Sentinel_Death"))

    set_prop(cdo, "max_move_speed", SENTINEL_MOVE_SPEED)
    set_prop(cdo, "attack_damage", SENTINEL_DAMAGE)
    set_prop(cdo, "tile_size", TILE_SIZE)
    set_prop(cdo, "attack_range_tiles", SENTINEL_RANGE_TILES)
    set_prop(cdo, "collision_radius", SENTINEL_COLLISION_RADIUS)
    set_prop(cdo, "collision_half_height", SENTINEL_COLLISION_HALF_HEIGHT)
    set_prop(cdo, "default_facing_direction", unreal.PTKFacingDirection.DOWN)

    # Identity, so the player health panel and the defeat banner name the guard
    # actually being played instead of whoever the HUD was first written for.
    set_prop(cdo, "guard_id", "Sentinel")
    set_prop(cdo, "guard_display_name", "Sentinel")

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
    if orb_blueprint is not None:
        set_prop(cdo, "projectile_class", orb_blueprint.generated_class())
    set_prop(cdo, "projectile_speed", ORB_SPEED)
    set_prop(cdo, "muzzle_forward_offset", MUZZLE_FORWARD)
    set_prop(cdo, "muzzle_height_offset", MUZZLE_HEIGHT)
    set_prop(cdo, "attack_impact_fraction", SENTINEL_RELEASE_FRACTION)

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", SENTINEL_MAX_HP)
    else:
        warn("could not reach BP_Sentinel's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Sentinel did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Sentinel ready")
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
    orb_pivots = set()
    orb_dims = set()
    total = 0
    for stem, _relative in full_layout():
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/SPR_Sentinel_" + stem)
        if sprite is None:
            ok = False
            fail("missing sprite SPR_Sentinel_" + stem)
            continue
        total += 1
        pivot = sprite.get_editor_property("custom_pivot_point")
        dimension = sprite.get_editor_property("source_dimension")
        if is_projectile(stem):
            orb_pivots.add((round(pivot.x), round(pivot.y)))
            orb_dims.add((round(dimension.x), round(dimension.y)))
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

    if orb_pivots == {(int(ORB_PIVOT), int(ORB_PIVOT))} and \
            orb_dims == {(ORB_SIZE, ORB_SIZE)}:
        info("PASS  15 projectile sprites are {0}x{0} at centre pivot ({1}, {1})".format(
            ORB_SIZE, int(ORB_PIVOT)))
    else:
        ok = False
        fail("projectile sprites inconsistent: pivots {0} dims {1}".format(
            orb_pivots, orb_dims))

    expected = [("Idle", 1, IDLE_FPS), ("Walk", WALK_FRAME_COUNT, WALK_FPS),
                ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS),
                ("Orb", ORB_FRAME_COUNT, ORB_FPS)]
    for anim, count, fps in expected:
        for direction in DIRECTIONS:
            name = "FB_Sentinel_{0}_{1}".format(anim, direction)
            fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
            if fb is None:
                ok = False
                fail("missing " + name)
                continue
            keys = fb.get_editor_property("key_frames")
            if len(keys) != count:
                ok = False
                fail("{0} has {1} frames, expected {2}".format(name, len(keys), count))
    for name, count in (("FB_Sentinel_Death", DEATH_FRAME_COUNT),
                        ("FB_Sentinel_Impact", IMPACT_FRAME_COUNT)):
        fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
        if fb is None or len(fb.get_editor_property("key_frames")) != count:
            ok = False
            fail("{0} missing or wrong length".format(name))
    if ok:
        info("PASS  18 flipbooks: 4 idle, 4 walk, 4 attack, 1 death, "
             "4 orb, 1 impact")

    orb_bp = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_Orb_Sentinel")
    if orb_bp is None:
        ok = False
        fail("BP_Orb_Sentinel missing")
    else:
        orb_cdo = unreal.get_default_object(orb_bp.generated_class())
        flight = orb_cdo.get_editor_property("flight_flipbooks")
        missing = [d for d in DIRECTIONS
                   if flight.get_editor_property(d.lower()) is None]
        if missing:
            ok = False
            fail("BP_Orb_Sentinel flight_flipbooks missing {0}".format(missing))
        if orb_cdo.get_editor_property("impact_flipbook") is None:
            ok = False
            fail("BP_Orb_Sentinel has no impact flipbook")
        for prop, want in (("splash_radius", ORB_SPLASH_RADIUS),
                           ("collision_radius", ORB_COLLISION_RADIUS)):
            got = orb_cdo.get_editor_property(prop)
            if abs(got - want) > 0.01:
                ok = False
                fail("BP_Orb_Sentinel {0} is {1}, expected {2}".format(prop, got, want))
        if not isinstance(orb_cdo, unreal.PTKProjectile):
            ok = False
            fail("BP_Orb_Sentinel does not derive from APTKProjectile")
        elif not missing:
            info("PASS  BP_Orb_Sentinel is an APTKProjectile with all 4 flight "
                 "directions and an impact burst")

    blueprint = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_Sentinel")
    if blueprint is None:
        ok = False
        fail("BP_Sentinel missing")
    else:
        cdo = unreal.get_default_object(blueprint.generated_class())
        health = cdo.get_editor_property("health_component")
        hp = health.get_editor_property("max_health") if health else 0.0
        checks = [("attack_damage", SENTINEL_DAMAGE),
                  ("max_move_speed", SENTINEL_MOVE_SPEED),
                  ("attack_range_tiles", SENTINEL_RANGE_TILES),
                  ("tile_size", TILE_SIZE),
                  ("attack_impact_fraction", SENTINEL_RELEASE_FRACTION),
                  ("projectile_speed", ORB_SPEED)]
        for prop, want in checks:
            got = cdo.get_editor_property(prop)
            if abs(got - want) > 0.01:
                ok = False
                fail("BP_Sentinel {0} is {1}, expected {2}".format(prop, got, want))
        if abs(hp - SENTINEL_MAX_HP) > 0.01:
            ok = False
            fail("BP_Sentinel MaxHealth is {0}, expected {1}".format(hp, SENTINEL_MAX_HP))
        for prop in ("idle_flipbooks", "walk_flipbooks", "attack_flipbooks"):
            value = cdo.get_editor_property(prop)
            missing = [d for d in DIRECTIONS
                       if value.get_editor_property(d.lower()) is None]
            if missing:
                ok = False
                fail("BP_Sentinel {0} missing {1}".format(prop, missing))
        if cdo.get_editor_property("death_flipbook") is None:
            ok = False
            fail("BP_Sentinel has no death flipbook")
        if cdo.get_editor_property("projectile_class") is None:
            ok = False
            fail("BP_Sentinel has no projectile class - he would swing, not shoot")
        for prop in ("default_mapping_context", "move_action", "attack_action"):
            if cdo.get_editor_property(prop) is None:
                ok = False
                fail("BP_Sentinel has no {0} - WASD would not reach him".format(prop))
        if str(cdo.get_editor_property("guard_id")) != "Sentinel":
            ok = False
            fail("BP_Sentinel guard_id is {0}, expected Sentinel".format(
                cdo.get_editor_property("guard_id")))
        if ok:
            info("PASS  BP_Sentinel: {0:.0f} HP, {1:.0f} damage, {2} tiles ({3:.0f} uu), "
                 "speed {4:.0f}".format(hp, SENTINEL_DAMAGE, SENTINEL_RANGE_TILES,
                                        SENTINEL_RANGE_TILES * TILE_SIZE, SENTINEL_MOVE_SPEED))
            info("PASS  BP_Sentinel fires BP_Orb_Sentinel at {0:.0f} uu/s, released at "
                 "{1:.3f} of the attack (frame 5 of 8)".format(
                     ORB_SPEED, SENTINEL_RELEASE_FRACTION))
            info("PASS  orb deals {0:.0f} in a {1:.0f} uu blast ({2} tiles), "
                 "sweep radius {3:.0f}".format(SENTINEL_DAMAGE, ORB_SPLASH_RADIUS,
                                               ORB_SPLASH_RADIUS / TILE_SIZE,
                                               ORB_COLLISION_RADIUS))
            info("PASS  BP_Sentinel carries IMC_PTK_Default, IA_Move and IA_Attack, "
                 "so WASD and the attack key reach him when possessed")
            # The point of the whole phase: Sentinel IS a guard, not a parallel
            # implementation. Proven by type, not by the asset's metadata.
            if isinstance(cdo, unreal.PTKGuardCharacter):
                info("PASS  BP_Sentinel is an APTKGuardCharacter - same class as Ravager "
                     "and Aegis, so health, facing, input, attack timing, death and "
                     "enemy targeting are inherited")
            else:
                ok = False
                fail("BP_Sentinel does not derive from APTKGuardCharacter")

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("Sentinel generation")
    info("=" * 62)

    textures = import_textures()
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    orb = create_orb_blueprint(flipbooks)
    create_blueprint(flipbooks, orb)
    verify()

    info("=" * 62)
    for key in ("textures", "sprites", "flipbooks", "blueprint"):
        info("{0:<10}: {1}".format(key, _summary[key]))
    info("{0:<10}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<10}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
