"""
Protect the King - 2D
Unreal Editor Python script: imports Reaver and wires up the assassin guard.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateReaver.py"

What it creates
---------------
  Textures    T_Reaver_*        76 textures, point-filtered, uncompressed
  Sprites     SPR_Reaver_*      76 sprites, pivot (96,179), PPU 1.0
  Flipbooks   FB_Reaver_Idle_*    4 flipbooks, 1 frame  @  8 FPS
              FB_Reaver_Walk_*    4 flipbooks, 8 frames @ 12 FPS
              FB_Reaver_Attack_*  4 flipbooks, 8 frames @ 14 FPS
              FB_Reaver_Death     1 flipbook,  8 frames @  9 FPS
  Blueprint   BP_Reaver         parented to APTKGuardCharacter

Re-running is safe: assets are updated in place, and nothing about Ravager,
Aegis, Wraith, Swarm Node, the King or the level is touched.


REAVER IS A MELEE GUARD, NOT A NEW SYSTEM
-----------------------------------------
BP_Reaver derives from APTKGuardCharacter, the same class Ravager and Aegis use,
and takes the ORIGINAL melee path - the swing resolves as a sphere overlap in
front of him at his impact frame. He does not touch Wraith's projectile system:
ProjectileClass is left unset, which is the single property that decides whether
a character shoots or swings.

He therefore inherits rather than re-implements: the shared UPTKHealthComponent,
facing, the Idle/Walk/Attack/Dead machine, impact-frame timing, the guard's
multi-target arc with its once-per-victim rule, player input, death handling,
and being recognised as a guard by enemy targeting and the King fallback.

He also has no shield defence - DefendFlipbooks is left empty, so StartDefend()
refuses and the skill stays Aegis-only.

Only the four numbers below, and his art, differ.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Contract - matches Tools/ExtractReaverAnimations.py and Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
FRAME_WIDTH = 224
FRAME_HEIGHT = 224
PIVOT_X = 112.0
PIVOT_Y = 200.0
PIXELS_PER_UNREAL_UNIT = 1.0

IDLE_FPS = 8.0
# Faster than the other guards' 10: he moves at 300 uu/s and a 10 FPS cycle at
# that speed reads as skating. 12 keeps his feet with him.
WALK_FPS = 12.0
# Faster than the other guards' 12, for the same reason - he is the quick one,
# and the swing should look it.
ATTACK_FPS = 14.0
DEATH_FPS = 9.0

DIRECTIONS = ["Down", "Up", "Left", "Right"]
WALK_FRAME_COUNT = 8
ATTACK_FRAME_COUNT = 8
DEATH_FRAME_COUNT = 8

# ---------------------------------------------------------------------------
# Prototype balance - Reaver is the assassin
# ---------------------------------------------------------------------------
# Ravager: 7000 HP, 25 damage, 240 uu/s, 3.5 tiles - the bruiser.
# Aegis:   9000 HP, 20 damage, 200 uu/s, 3.5 tiles - the tank.
# Wraith:  5000 HP, 50 damage, 270 uu/s, 7.0 tiles - the archer.
# Reaver:  5500 HP, 35 damage, 300 uu/s, 3.5 tiles - the fastest thing on the
#          field and the hardest-hitting melee, paid for with the thinnest
#          health pool of any melee guard.
REAVER_MAX_HP = 5500.0
REAVER_DAMAGE = 35.0
REAVER_MOVE_SPEED = 300.0
TILE_SIZE = 64.0
REAVER_RANGE_TILES = 3.5

# Deliberately identical to every other guard's. The capsule is the combat
# geometry, so keeping it the same means each measured difference between guards
# is one of the four numbers above and not an accident of collision size.
REAVER_COLLISION_RADIUS = 14.0
REAVER_COLLISION_HALF_HEIGHT = 14.0

# Frame 5 of 8, which begins at 4/8 - the project's melee standard, shared with
# Ravager and Aegis. Measured: his blade energy peaks at frame 5 facing Down and
# Up and at frame 4 in profile, so 5 is the median of the four directions and is
# never more than one frame (0.07s at 14 FPS) from the true contact.
REAVER_IMPACT_FRACTION = 0.5

INPUT_DIR = "/Game/PTK/Input"
MAPPING_CONTEXT = INPUT_DIR + "/IMC_PTK_Default"
MOVE_ACTION = INPUT_DIR + "/IA_Move"
ATTACK_ACTION = INPUT_DIR + "/IA_Attack"

REAVER_ROOT = "/Game/PTK/Characters/Guards/Reaver"
TEXTURE_DIR = REAVER_ROOT + "/Textures"
SPRITE_DIR = REAVER_ROOT + "/Sprites"
FLIPBOOK_DIR = REAVER_ROOT + "/Flipbooks"
BLUEPRINT_DIR = REAVER_ROOT + "/Blueprints"

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
    return layout


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures():
    ensure_directory(TEXTURE_DIR)
    root = os.path.join(project_dir(), "ArtSource", "Characters", "Guards",
                        "Reaver", "Frames")

    tasks = []
    wanted = []
    for stem, relative in frame_layout():
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            fail("missing source frame " + relative)
            continue
        asset_name = "T_Reaver_" + stem
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
            name = "FB_Reaver_{0}_{1}".format(anim, direction)
            fb = build(name, ["SPR_Reaver_{0}_{1}_{2:02d}".format(anim, direction, i)
                              for i in range(1, count + 1)], fps)
            if fb:
                flipbooks[name] = fb

    for direction in DIRECTIONS:
        name = "FB_Reaver_Idle_" + direction
        fb = build(name, ["SPR_Reaver_Idle_" + direction], IDLE_FPS)
        if fb:
            flipbooks[name] = fb

    death = build("FB_Reaver_Death",
                  ["SPR_Reaver_Death_{0:02d}".format(i)
                   for i in range(1, DEATH_FRAME_COUNT + 1)], DEATH_FPS)
    if death:
        flipbooks["FB_Reaver_Death"] = death

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


def create_blueprint(flipbooks):
    guard_class = getattr(unreal, "PTKGuardCharacter", None)
    if guard_class is None:
        fail("APTKGuardCharacter is not loaded - compile the C++ module first")
        return None

    ensure_directory(BLUEPRINT_DIR)
    path = BLUEPRINT_DIR + "/BP_Reaver"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", guard_class)
        blueprint = _asset_tools.create_asset(
            "BP_Reaver", BLUEPRINT_DIR, unreal.Blueprint, factory)
    if blueprint is None:
        fail("could not create BP_Reaver")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Reaver class defaults")
        return blueprint

    set_prop(cdo, "idle_flipbooks", directional(flipbooks, "FB_Reaver_Idle_"))
    set_prop(cdo, "walk_flipbooks", directional(flipbooks, "FB_Reaver_Walk_"))
    set_prop(cdo, "attack_flipbooks", directional(flipbooks, "FB_Reaver_Attack_"))
    set_prop(cdo, "death_flipbook", flipbooks.get("FB_Reaver_Death"))

    set_prop(cdo, "max_move_speed", REAVER_MOVE_SPEED)
    set_prop(cdo, "attack_damage", REAVER_DAMAGE)
    set_prop(cdo, "tile_size", TILE_SIZE)
    set_prop(cdo, "attack_range_tiles", REAVER_RANGE_TILES)
    set_prop(cdo, "attack_impact_fraction", REAVER_IMPACT_FRACTION)
    set_prop(cdo, "collision_radius", REAVER_COLLISION_RADIUS)
    set_prop(cdo, "collision_half_height", REAVER_COLLISION_HALF_HEIGHT)
    set_prop(cdo, "default_facing_direction", unreal.PTKFacingDirection.DOWN)

    # Identity, so the health panel reads REAVER and the banner REAVER DEFEATED
    # without a single character name being written into the HUD.
    set_prop(cdo, "guard_id", "Reaver")
    set_prop(cdo, "guard_display_name", "Reaver")

    for prop, path_ in (("default_mapping_context", MAPPING_CONTEXT),
                        ("move_action", MOVE_ACTION),
                        ("attack_action", ATTACK_ACTION)):
        asset = unreal.EditorAssetLibrary.load_asset(path_)
        if asset is None:
            warn("input asset missing: " + path_)
            continue
        set_prop(cdo, prop, asset)

    health = cdo.get_editor_property("health_component")
    if health:
        set_prop(health, "max_health", REAVER_MAX_HP)
    else:
        warn("could not reach BP_Reaver's health component to set MaxHealth")

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Reaver did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Reaver ready")
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
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/SPR_Reaver_" + stem)
        if sprite is None:
            ok = False
            fail("missing sprite SPR_Reaver_" + stem)
            continue
        total += 1
        pivot = sprite.get_editor_property("custom_pivot_point")
        pivots.add((round(pivot.x), round(pivot.y)))
        dimension = sprite.get_editor_property("source_dimension")
        dims.add((round(dimension.x), round(dimension.y)))

    if pivots == {(int(PIVOT_X), int(PIVOT_Y))} and dims == {(FRAME_WIDTH, FRAME_HEIGHT)}:
        info("PASS  {0} sprites are {1}x{2} at pivot ({3}, {4})".format(
            total, FRAME_WIDTH, FRAME_HEIGHT, int(PIVOT_X), int(PIVOT_Y)))
    else:
        ok = False
        fail("sprites inconsistent: pivots {0} dims {1}".format(pivots, dims))

    expected = [("Idle", 1, IDLE_FPS), ("Walk", WALK_FRAME_COUNT, WALK_FPS),
                ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS)]
    for anim, count, fps in expected:
        for direction in DIRECTIONS:
            name = "FB_Reaver_{0}_{1}".format(anim, direction)
            fb = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
            if fb is None:
                ok = False
                fail("missing " + name)
                continue
            keys = fb.get_editor_property("key_frames")
            if len(keys) != count:
                ok = False
                fail("{0} has {1} frames, expected {2}".format(name, len(keys), count))
    death = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/FB_Reaver_Death")
    if death is None or len(death.get_editor_property("key_frames")) != DEATH_FRAME_COUNT:
        ok = False
        fail("FB_Reaver_Death missing or wrong length")
    if ok:
        info("PASS  13 flipbooks: 4 idle, 4 walk, 4 attack, 1 death")

    blueprint = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_DIR + "/BP_Reaver")
    if blueprint is None:
        ok = False
        fail("BP_Reaver missing")
    else:
        cdo = unreal.get_default_object(blueprint.generated_class())
        health = cdo.get_editor_property("health_component")
        hp = health.get_editor_property("max_health") if health else 0.0
        checks = [("attack_damage", REAVER_DAMAGE),
                  ("max_move_speed", REAVER_MOVE_SPEED),
                  ("attack_range_tiles", REAVER_RANGE_TILES),
                  ("tile_size", TILE_SIZE),
                  ("attack_impact_fraction", REAVER_IMPACT_FRACTION)]
        for prop, want in checks:
            got = cdo.get_editor_property(prop)
            if abs(got - want) > 0.01:
                ok = False
                fail("BP_Reaver {0} is {1}, expected {2}".format(prop, got, want))
        if abs(hp - REAVER_MAX_HP) > 0.01:
            ok = False
            fail("BP_Reaver MaxHealth is {0}, expected {1}".format(hp, REAVER_MAX_HP))
        for prop in ("idle_flipbooks", "walk_flipbooks", "attack_flipbooks"):
            value = cdo.get_editor_property(prop)
            missing = [d for d in DIRECTIONS
                       if value.get_editor_property(d.lower()) is None]
            if missing:
                ok = False
                fail("BP_Reaver {0} missing {1}".format(prop, missing))
        if cdo.get_editor_property("death_flipbook") is None:
            ok = False
            fail("BP_Reaver has no death flipbook")
        for prop in ("default_mapping_context", "move_action", "attack_action"):
            if cdo.get_editor_property(prop) is None:
                ok = False
                fail("BP_Reaver has no {0} - WASD would not reach him".format(prop))
        if str(cdo.get_editor_property("guard_id")) != "Reaver":
            ok = False
            fail("BP_Reaver guard_id is {0}, expected Reaver".format(
                cdo.get_editor_property("guard_id")))
        # He is a MELEE guard: these two must stay empty, or he would be firing
        # arrows or blocking damage like somebody else.
        if cdo.get_editor_property("projectile_class") is not None:
            ok = False
            fail("BP_Reaver has a projectile class - he must swing, not shoot")
        defend = cdo.get_editor_property("defend_flipbooks")
        if any(defend.get_editor_property(d.lower()) is not None for d in DIRECTIONS):
            ok = False
            fail("BP_Reaver has defend flipbooks - the shield skill is Aegis-only")

        if ok:
            info("PASS  BP_Reaver: {0:.0f} HP, {1:.0f} damage, {2} tiles ({3:.0f} uu), "
                 "speed {4:.0f}".format(hp, REAVER_DAMAGE, REAVER_RANGE_TILES,
                                        REAVER_RANGE_TILES * TILE_SIZE, REAVER_MOVE_SPEED))
            info("PASS  BP_Reaver is melee: no projectile class, no defend art - he "
                 "uses the original guard swing at frame 5 of 8")
            info("PASS  BP_Reaver carries IMC_PTK_Default, IA_Move and IA_Attack, and "
                 "is named Reaver for the HUD")
            if isinstance(cdo, unreal.PTKGuardCharacter):
                info("PASS  BP_Reaver is an APTKGuardCharacter - same class as Ravager, "
                     "Aegis and Wraith, so health, facing, input, melee timing, death "
                     "and enemy targeting are inherited")
            else:
                ok = False
                fail("BP_Reaver does not derive from APTKGuardCharacter")

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("Reaver generation")
    info("=" * 62)

    textures = import_textures()
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    create_blueprint(flipbooks)
    verify()

    info("=" * 62)
    for key in ("textures", "sprites", "flipbooks", "blueprint"):
        info("{0:<10}: {1}".format(key, _summary[key]))
    info("{0:<10}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<10}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
