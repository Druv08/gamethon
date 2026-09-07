"""
Protect the King - 2D
Builds the real gameplay level from the supplied map artwork.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_BuildBattlefield.py"

What it does
------------
1. Imports both map images. The CLEAN one becomes the ground the player walks
   on; the LABELLED one becomes the minimap, where naming the places is the
   point rather than clutter under the characters' feet.
2. Creates L_PTK_Battlefield and lays out the battlefield: the ground plane,
   the King on his core, five guards on their posts, five attackable bases,
   four corner spawn portals, the battlefield descriptor and the wave manager.
3. Applies the stronger enemy balance to the five enemy Blueprints.
4. Points the project's default map at the new level.

Re-running is safe: the level is rebuilt from scratch each time.


WORLD SCALE - WHY 3 UNITS PER PIXEL
-----------------------------------
The artwork is 1672x941. At 3 world units per pixel the battlefield is
5016 x 2823 units, which puts a 224-unit guard sprite at about 1/7th the width
of a base platform - a character standing ON a base rather than covering it.

The aspect ratio is taken from the PNG and never adjusted, so the painted roads
stay exactly where the lane graph in APTKBattlefield expects them. Both sides
derive from the same normalised coordinates; changing one without the other is
what would break the pathing, and neither is hand-authored in world units.

The camera then shows 30% of 5016 = ~1505 units, which is the League-like
window the spec asks for: the map does not fit on screen and cannot be made to.
"""

import json
import os
import unreal

_report = []

SRC = r"C:\Users\druvk\Downloads\gamethon pics\design 2d pics"
CLEAN_PNG = os.path.join(SRC, "MAP WITHOUT BANNERS.png")
LABELLED_PNG = os.path.join(SRC, "MAP.png")

MAPS = "/Game/PTK/Maps"
LEVEL = MAPS + "/L_PTK_Battlefield"
GUARD_ROOT = "/Game/PTK/Characters/Guards"
ENEMY_ROOT = "/Game/PTK/Characters/Enemies"

# The artwork, and the scale that turns it into a world.
TEX_W, TEX_H = 1672, 941
UNITS_PER_PIXEL = 3.0
MAP_W = TEX_W * UNITS_PER_PIXEL          # 5016
MAP_H = TEX_H * UNITS_PER_PIXEL          # 2823

# Far enough behind the play plane to sit under every character: depth sorting
# offsets a character by at most MapHeight/2 * DepthSortScale = ~141 units.
GROUND_Y = 300.0

LIB = unreal.EditorAssetLibrary
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()

_summary = {"placed": 0, "warnings": [], "errors": []}


def info(msg):
    # Also captured to a file: unreal.log lands at Display verbosity, which a
    # commandlet run does not print, so a log-only report would be invisible.
    _report.append(msg)
    unreal.log("[PTK] " + msg)


def warn(msg):
    _summary["warnings"].append(msg)
    _report.append("WARNING: " + msg)
    unreal.log_warning("[PTK] " + msg)


def fail(msg):
    _summary["errors"].append(msg)
    _report.append("ERROR: " + msg)
    unreal.log_error("[PTK] " + msg)


def write_report():
    out = os.path.join(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()),
        "Tools", "_Output")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "battlefield_build.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(_report) + "\n")
    with open(os.path.join(out, "battlefield_build.json"), "w", encoding="utf-8") as handle:
        json.dump({"map_width": MAP_W, "map_height": MAP_H,
                   "placed": _summary["placed"],
                   "warnings": _summary["warnings"],
                   "errors": _summary["errors"]}, handle, indent=2)


def to_world(u, v):
    """Normalised artwork coords -> world XZ.

    Screen-right is -X and screen-up is +Z, so BOTH axes flip relative to the
    image. This must stay identical to APTKBattlefield::NormalisedToWorld.
    """
    return (-(u - 0.5) * MAP_W, (0.5 - v) * MAP_H)


# Read off the artwork. Same numbers as BuildDefaultLanes in C++.
POSTS = {
    "Aegis":    (0.368, 0.225),
    "Wraith":   (0.632, 0.222),
    "Reaver":   (0.283, 0.560),
    "Ravager":  (0.718, 0.558),
    "Sentinel": (0.500, 0.795),
}
KING_AT = (0.500, 0.475)

# Named for what the PLAYER sees, not for the sign of world X - the image's
# left-hand corners are at +X, and a portal called "East" that appears on the
# left of the screen would be actively misleading.
PORTALS = [
    ("NorthWest", "North-West", 0.085, 0.330),
    ("NorthEast", "North-East", 0.915, 0.330),
    ("SouthWest", "South-West", 0.093, 0.790),
    ("SouthEast", "South-East", 0.912, 0.790),
]

# HP, damage. Roles, speeds and ranges are left alone; wave scaling still
# multiplies on top of these at spawn time.
ENEMY_BALANCE = {
    "SwarmNode":   (180.0, 24.0),
    "Infiltrator": (220.0, 32.0),
    "Hijacker":    (300.0, 36.0),
    "Encrypter":   (600.0, 50.0),
    "Exfiltrator": (260.0, 32.0),
}

# Cut from the destroyed-state render by Tools/ExtractDestroyedBases.py.
RUINS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ArtSource", "Map", "DestroyedBases")

BASE_HEALTH = 2500.0

# A guard stands just in front of its base rather than inside it, so the two are
# separately clickable, separately targetable and visually distinct.
GUARD_OFFSET_Z = -70.0


def actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def save(asset):
    LIB.save_loaded_asset(asset, only_if_is_dirty=False)


# ---------------------------------------------------------------------------
# 1. Map artwork
# ---------------------------------------------------------------------------
def import_texture(png, name):
    package = MAPS + "/" + name
    if LIB.does_asset_exist(package):
        LIB.delete_asset(package)

    task = unreal.AssetImportTask()
    task.filename = png
    task.destination_path = MAPS
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    ASSETS.import_asset_tasks([task])

    texture = LIB.load_asset(package)
    if texture is None:
        fail("could not import " + png)
        return None

    # The map is a painted illustration rather than pixel art, so ordinary
    # compression and filtering are right for it - the point-filtered,
    # uncompressed treatment the character frames get would only cost memory
    # here. Streaming is off so the ground is never briefly blurry on load.
    texture.set_editor_property("never_stream", True)
    save(texture)
    info("imported {0} ({1}x{2})".format(
        name, texture.blueprint_get_size_x(), texture.blueprint_get_size_y()))
    return texture


def load_or_create_sprite(name):
    """Existing sprite if there is one, otherwise a new empty one."""
    package = MAPS + "/" + name
    existing = LIB.load_asset(package) if LIB.does_asset_exist(package) else None
    if existing is not None:
        return existing
    return ASSETS.create_asset(name, MAPS, unreal.PaperSprite,
                               unreal.PaperSpriteFactory())


def build_ruins_sprites():
    """One texture + sprite per destroyed base, keyed by guard id."""
    out = {}
    for name in POSTS:
        png = os.path.join(RUINS_DIR, "Destroyed_{0}.png".format(name))
        if not os.path.isfile(png):
            warn("no ruins art for {0} - run Tools/ExtractDestroyedBases.py".format(name))
            continue

        texture = import_texture(png, "T_PTK_Ruins_" + name)
        if texture is None:
            continue

        # Load-or-create, never delete-then-create: the placed bases hold
        # references to these sprites, so deleting one that is already in the
        # level fails and leaves nothing to put back.
        sprite = load_or_create_sprite("SPR_Ruins_" + name)
        if sprite is None:
            fail("could not create SPR_Ruins_" + name)
            continue

        width = texture.blueprint_get_size_x()
        height = texture.blueprint_get_size_y()
        sprite.set_editor_property("source_texture", texture)
        sprite.set_editor_property("source_uv", unreal.Vector2D(0.0, 0.0))
        sprite.set_editor_property("source_dimension",
                                   unreal.Vector2D(float(width), float(height)))
        # The same pixels-per-unit as the ground, so the ruins come out at
        # exactly the size of the platform they were cut from.
        sprite.set_editor_property("pixels_per_unreal_unit", 1.0 / UNITS_PER_PIXEL)
        sprite.set_editor_property("sprite_collision_domain", unreal.SpriteCollisionMode.NONE)
        save(sprite)

        out[name] = sprite
        info("ruins sprite {0} ({1}x{2} px)".format(name, width, height))
    return out


def build_ground_sprite(texture):
    sprite = load_or_create_sprite("SPR_Battlefield")
    if sprite is None:
        fail("could not create SPR_Battlefield")
        return None

    # The factory's fields are plain C++ members, not UPROPERTYs, so it cannot
    # be pre-configured from Python. The source rectangle is set here instead;
    # assigning these fires PostEditChangeProperty, which rebuilds the geometry.
    sprite.set_editor_property("source_texture", texture)
    sprite.set_editor_property("source_uv", unreal.Vector2D(0.0, 0.0))
    sprite.set_editor_property("source_dimension",
                               unreal.Vector2D(float(TEX_W), float(TEX_H)))

    # Pixels per unreal unit, NOT an actor scale. Sizing the sprite itself means
    # the ground actor stays at scale 1 and its transform reads as world units.
    sprite.set_editor_property("pixels_per_unreal_unit", 1.0 / UNITS_PER_PIXEL)
    sprite.set_editor_property("sprite_collision_domain", unreal.SpriteCollisionMode.NONE)
    save(sprite)
    info("SPR_Battlefield at {0:.4f} PPU -> {1:.0f} x {2:.0f} uu".format(
        1.0 / UNITS_PER_PIXEL, MAP_W, MAP_H))
    return sprite


# ---------------------------------------------------------------------------
# 2. The level
# ---------------------------------------------------------------------------
def place(cls, x, z, label, y=0.0):
    actor = actors().spawn_actor_from_class(cls, unreal.Vector(x, y, z), unreal.Rotator())
    if actor is None:
        fail("could not place " + label)
        return None
    actor.set_actor_label(label)
    _summary["placed"] += 1
    return actor


def guard_class(name):
    bp = LIB.load_asset("{0}/{1}/Blueprints/BP_{1}".format(GUARD_ROOT, name))
    return bp.generated_class() if bp else None


def enemy_class(name):
    if name == "SwarmNode":
        bp = LIB.load_asset("/Game/PTK/Characters/Enemies/SwarmNode/Blueprints/BP_SwarmNode")
    else:
        bp = LIB.load_asset("{0}/{1}/Blueprints/BP_{1}".format(ENEMY_ROOT, name))
    return bp.generated_class() if bp else None


def build_level(sprite, ruins):
    level_sub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

    # Idempotent by loading and emptying rather than by deleting and
    # recreating. new_level refuses to overwrite an existing asset, and a
    # delete leaves the .umap on disk long enough for the next create to trip
    # over it - so re-running would fail on every run after the first.
    if LIB.does_asset_exist(LEVEL):
        if not level_sub.load_level(LEVEL):
            fail("could not open " + LEVEL)
            return
        existing = actors().get_all_level_actors()
        for actor in existing:
            actors().destroy_actor(actor)
        info("emptied the existing L_PTK_Battlefield ({0} actors)".format(len(existing)))
    elif not level_sub.new_level(LEVEL):
        fail("could not create " + LEVEL)
        return

    # --- ground -----------------------------------------------------
    ground = place(unreal.PaperSpriteActor, 0.0, 0.0, "Battlefield_Ground", GROUND_Y)
    if ground:
        component = ground.get_editor_property("render_component")
        # set_editor_property, NOT the component's set_sprite(): the setter does
        # not mark the package dirty from editor scripting, so the assignment is
        # dropped when the level is saved and the ground loads back as None -
        # which renders as a black void with the characters floating on it.
        component.set_editor_property("source_sprite", sprite)
        # Behind everything that sorts by depth, and never itself sorted.
        component.set_editor_property("translucency_sort_priority", -1000)

        assigned = component.get_editor_property("source_sprite")
        if assigned is None:
            fail("the ground sprite did not stick - the map would render black")
        else:
            info("ground sprite assigned: {0}".format(assigned.get_name()))

    # --- descriptor + wave manager ----------------------------------
    place(unreal.PTKBattlefield, 0.0, 0.0, "Battlefield")
    waves = place(unreal.PTKWaveManager, 0.0, 0.0, "WaveManager")

    # --- King -------------------------------------------------------
    king_bp = LIB.load_asset("/Game/PTK/Characters/King/Blueprints/BP_King")
    kx, kz = to_world(*KING_AT)
    if king_bp:
        place(king_bp.generated_class(), kx, kz, "King")
    else:
        fail("BP_King not found")

    # --- bases ------------------------------------------------------
    for name, (u, v) in POSTS.items():
        x, z = to_world(u, v)
        base = place(unreal.PTKGuardBase, x, z, "Base_" + name)
        if base:
            base.set_editor_property("guard_id", name)
            base.set_editor_property("base_display_name", unreal.Text(name + " Base"))
            base.set_editor_property("max_health", BASE_HEALTH)
            if name in ruins:
                base.set_editor_property("destroyed_sprite", ruins[name])

    # --- guards -----------------------------------------------------
    #
    # Ravager is NOT placed: he is spawned by the game mode at the PlayerStart
    # and possessed by the player. Placing him too would put two Ravagers on the
    # field. See PTK_SetupGuardPosts.py for why placement decides who is AI.
    for name, (u, v) in POSTS.items():
        x, z = to_world(u, v)
        if name == "Ravager":
            place(unreal.PlayerStart, x, z + GUARD_OFFSET_Z, "PlayerStart_Ravager")
            continue
        cls = guard_class(name)
        if cls is None:
            fail("BP_" + name + " not found")
            continue
        place(cls, x, z + GUARD_OFFSET_Z, "Guard_" + name)

    # --- spawn portals ----------------------------------------------
    for pid, display, u, v in PORTALS:
        x, z = to_world(u, v)
        portal = place(unreal.PTKSpawnPortal, x, z, "Portal_" + pid)
        if portal:
            portal.set_editor_property("portal_id", pid)
            portal.set_editor_property("portal_display_name", unreal.Text(display + " Portal"))

    # --- wave manager enemy table -----------------------------------
    if waves:
        table = unreal.Map(unreal.Name, unreal.SoftClassPath)
        types = {}
        for name in ENEMY_BALANCE:
            cls = enemy_class(name)
            if cls is None:
                warn("BP_" + name + " not found - it cannot appear in a wave")
                continue
            types[unreal.Name(name)] = cls
        try:
            waves.set_editor_property("enemy_types", types)
            info("wave manager knows {0} enemy types".format(len(types)))
        except Exception as exc:  # noqa: BLE001
            fail("could not set enemy_types: {0}".format(exc))
        del table

    # --- game mode --------------------------------------------------
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world_settings = editor.get_editor_world().get_world_settings()
    gm = unreal.load_class(None, "/Script/ProtectTheKing2D.PTKGameModeBase")
    if gm:
        world_settings.set_editor_property("default_game_mode", gm)

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    info("level saved: " + LEVEL)


# ---------------------------------------------------------------------------
# 3. Enemy balance
# ---------------------------------------------------------------------------
def apply_balance():
    for name, (hp, damage) in ENEMY_BALANCE.items():
        if name == "SwarmNode":
            bp = LIB.load_asset("/Game/PTK/Characters/Enemies/SwarmNode/Blueprints/BP_SwarmNode")
        else:
            bp = LIB.load_asset("{0}/{1}/Blueprints/BP_{1}".format(ENEMY_ROOT, name))
        if bp is None:
            warn("BP_" + name + " not found - balance not applied")
            continue
        cdo = unreal.get_default_object(bp.generated_class())
        cdo.set_editor_property("attack_damage", damage)
        cdo.get_editor_property("health_component").set_editor_property("max_health", hp)

        # Enemies must cross a 5000-unit map to reach anything. The old value
        # was sized for a test arena where everything started in sight.
        cdo.set_editor_property("detection_range", 2600.0)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        save(bp)
        info("balance | {0:<12s} HP {1:>5.0f}  DMG {2:>4.0f}".format(name, hp, damage))


# ---------------------------------------------------------------------------
# 4. Default map
# ---------------------------------------------------------------------------
def set_default_map():
    ini = os.path.join(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()),
        "Config", "DefaultEngine.ini")
    with open(ini, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    target = "{0}.L_PTK_Battlefield".format(LEVEL)
    out = []
    for line in lines:
        if line.startswith("EditorStartupMap="):
            out.append("EditorStartupMap={0}\n".format(target))
        elif line.startswith("GameDefaultMap="):
            out.append("GameDefaultMap={0}\n".format(target))
        else:
            out.append(line)
    with open(ini, "w", encoding="utf-8") as handle:
        handle.writelines(out)
    info("default map -> " + target)


# ---------------------------------------------------------------------------
# 5. Verification
# ---------------------------------------------------------------------------
def verify():
    info("")
    info("-" * 64)
    ok = True

    found = {}
    for actor in actors().get_all_level_actors():
        found.setdefault(type(actor).__name__, []).append(actor)

    def expect(cls_name, count, what):
        nonlocal ok
        got = len(found.get(cls_name, []))
        if got != count:
            ok = False
            fail("{0}: expected {1}, found {2}".format(what, count, got))
        else:
            info("PASS  {0}: {1}".format(what, got))

    expect("PTKBattlefield", 1, "battlefield descriptor")
    expect("PTKWaveManager", 1, "wave manager")
    expect("PTKGuardBase", 5, "guard bases")
    expect("PTKSpawnPortal", 4, "spawn portals")
    expect("PlayerStart", 1, "player start")

    guards = [a for a in actors().get_all_level_actors()
              if isinstance(a, unreal.PTKGuardCharacter)]
    if len(guards) != 4:
        ok = False
        fail("placed guards: expected 4 (Ravager is spawned), found {0}".format(len(guards)))
    else:
        info("PASS  placed AI guards: 4 (+ Ravager spawned at the PlayerStart)")

    kings = [a for a in actors().get_all_level_actors()
             if isinstance(a, unreal.PTKKingCharacter)]
    if len(kings) != 1:
        ok = False
        fail("kings: expected 1, found {0}".format(len(kings)))
    else:
        info("PASS  King placed at the core")

    # Nothing may spawn on top of anything else.
    points = []
    for actor in actors().get_all_level_actors():
        label = actor.get_actor_label()
        if label.startswith(("Guard_", "Base_", "Portal_", "King", "PlayerStart")):
            points.append((label, actor.get_actor_location()))
    closest = None
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            d = (points[i][1] - points[j][1]).length()
            if closest is None or d < closest[0]:
                closest = (d, points[i][0], points[j][0])
    if closest and closest[0] < 40.0:
        ok = False
        fail("{0} and {1} are only {2:.0f} uu apart".format(closest[1], closest[2], closest[0]))
    elif closest:
        info("PASS  nothing stacked - closest pair {0}/{1} at {2:.0f} uu"
             .format(closest[1], closest[2], closest[0]))

    info("-" * 64)
    info("MAP  {0:.0f} x {1:.0f} uu   camera ortho {2:.0f}  ({3:.0f}% of width)"
         .format(MAP_W, MAP_H, MAP_W * 0.30, 30.0))
    info("BUILD {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 64)
    info("Building the real gameplay battlefield")
    info("=" * 64)

    clean = import_texture(CLEAN_PNG, "T_PTK_Battlefield")
    import_texture(LABELLED_PNG, "T_PTK_Battlefield_Minimap")
    if clean is None:
        fail("no ground artwork - aborting")
        return

    sprite = build_ground_sprite(clean)
    if sprite is None:
        return

    ruins = build_ruins_sprites()
    apply_balance()
    build_level(sprite, ruins)
    verify()
    set_default_map()

    info("=" * 64)
    info("placed  : {0}".format(_summary["placed"]))
    info("warnings: {0}".format(len(_summary["warnings"])))
    info("errors  : {0}".format(len(_summary["errors"])))
    info("=" * 64)
    write_report()


main()
