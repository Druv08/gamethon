"""
Protect the King - 2D
Unreal Editor Python script: builds every Phase 1 asset from source PNGs.

RUN THIS INSIDE THE UNREAL EDITOR, not from a normal shell:
    Window > Developer Tools > Output Log, switch the entry box to "Python",
    then run:
        exec(open(r"<ProjectDir>/Tools/PTK_GenerateAssets.py").read())

    or from a terminal:
        UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
            -run=pythonscript -script="<ProjectDir>/Tools/PTK_GenerateAssets.py"

What it creates
---------------
  Textures    T_Ravager_*            68 textures, point-filtered, uncompressed
  Sprites     SPR_Ravager_*          68 sprites, feet pivot (96,179), PPU 1.0
  Flipbooks   FB_Ravager_Idle_*      4 flipbooks, 1 frame each  @  8 FPS
              FB_Ravager_Walk_*      4 flipbooks, 8 frames each @ 10 FPS
              FB_Ravager_Attack_*    4 flipbooks, 8 frames each @ 12 FPS
  Input       IA_Move                Axis2D action
              IA_Attack              digital action
              IMC_PTK_Default        WASD + left stick, Space + LMB
  Level       L_PTK_TestGround       floor, walls, obstacles, PlayerStart
  Blueprint   BP_Ravager             only if the C++ module is compiled

The script is idempotent: re-running it updates existing assets in place.

Source art
----------
All 68 frames come from ArtSource/Characters/Guards/Ravager/Frames, written by
Tools/ExtractRavagerAnimations.py. There is no placeholder fallback - a frame
that is missing stops the run rather than quietly importing a dev dummy.
"""

import os

import unreal


# ---------------------------------------------------------------------------
# Project conventions - keep in sync with Docs/SPRITE_SPEC.md
# ---------------------------------------------------------------------------
# Every Ravager frame - idle, walk and attack - shares one canvas and one
# pivot. 128x128 held the idle art but cannot hold the animations at the same
# body scale: the raised attack axe needs 152 px above the feet and the walk
# axe 71 px to the side. Ravager is drawn at exactly the same size as before,
# with more transparent padding around him. See Docs/SPRITE_SPEC.md.
FRAME_WIDTH = 224
FRAME_HEIGHT = 224

# Feet anchor, in texture pixels from the top-left of the frame.
PIVOT_X = 112.0
PIVOT_Y = 200.0

# 1 source pixel == 1 Unreal unit, everywhere, for everything.
PIXELS_PER_UNREAL_UNIT = 1.0

IDLE_FPS = 8.0

# 8 frames at 10 FPS = a 0.8 s stride. Independent of MaxMoveSpeed by design:
# tuning how the walk reads must never change how fast Ravager travels.
WALK_FPS = 10.0

# 8 frames at 12 FPS = a 0.667 s swing - deliberately quicker than the walk so
# the attack lands with more force.
ATTACK_FPS = 12.0

DIRECTIONS = ["Down", "Up", "Left", "Right"]
WALK_FRAME_COUNT = 8
ATTACK_FRAME_COUNT = 8

# Ravager now has real 8-frame walk and attack art in every direction, so the
# placeholder stand-in that used to fill the walk flipbooks is gone. The old
# developer dummies live on in ArtSource/_TempDevArt and are referenced by
# nothing - see DEPRECATED.md there.

# Content paths
RAVAGER_ROOT = "/Game/PTK/Characters/Guards/Ravager"
TEXTURE_DIR = RAVAGER_ROOT + "/Textures"
SPRITE_DIR = RAVAGER_ROOT + "/Sprites"
FLIPBOOK_DIR = RAVAGER_ROOT + "/Flipbooks"
BLUEPRINT_DIR = RAVAGER_ROOT + "/Blueprints"
INPUT_DIR = "/Game/PTK/Input"
MAPS_DIR = "/Game/PTK/Maps"
CORE_DIR = "/Game/PTK/Core"

LEVEL_PATH = MAPS_DIR + "/L_PTK_TestGround"

CUBE_MESH = "/Engine/BasicShapes/Cube.Cube"

_asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

_summary = {
    "textures": 0,
    "sprites": 0,
    "flipbooks": 0,
    "input": 0,
    "level": 0,
    "blueprint": 0,
    "warnings": [],
    "errors": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def info(message):
    unreal.log("[PTK] " + message)


def warn(message):
    _summary["warnings"].append(message)
    unreal.log_warning("[PTK] " + message)


def fail(message):
    _summary["errors"].append(message)
    unreal.log_error("[PTK] " + message)


def set_prop(obj, name, value):
    """set_editor_property that reports instead of exploding."""
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as exc:  # noqa: BLE001 - we want every failure reported
        warn("could not set '{0}' on {1}: {2}".format(name, obj.get_name(), exc))
        return False


def project_dir():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())


def frame_layout():
    """
    Every frame this character needs, as (filename, relative source path).

    The art is filed by animation and direction rather than in one flat folder,
    because 68 frames in a single directory is unreadable and because the next
    ten characters will follow the same shape:

        Frames/Idle/Idle_<Dir>.png
        Frames/Walk/<Dir>/Walk_<Dir>_NN.png
        Frames/Attack/<Dir>/Attack_<Dir>_NN.png
    """
    layout = []
    for direction in DIRECTIONS:
        name = "Idle_{0}.png".format(direction)
        layout.append((name, os.path.join("Idle", name)))
    for anim, count in (("Walk", WALK_FRAME_COUNT), ("Attack", ATTACK_FRAME_COUNT)):
        for direction in DIRECTIONS:
            for index in range(1, count + 1):
                name = "{0}_{1}_{2:02d}.png".format(anim, direction, index)
                layout.append((name, os.path.join(anim, direction, name)))
    return layout


def resolve_frame_sources():
    """
    Locates all 68 finished frames. Returns {filename: (path, is_final)}.

    There is no placeholder fallback any more. Ravager's art is complete, and
    silently substituting a developer dummy for a frame that failed to generate
    is exactly the kind of thing that reaches a play session unnoticed - a
    missing frame should stop the build instead.
    """
    root = project_dir()
    final_dir = os.path.join(root, "ArtSource", "Characters", "Guards", "Ravager", "Frames")

    sources = {}
    for name, relative in frame_layout():
        path = os.path.join(final_dir, relative)
        if not os.path.isfile(path):
            fail("no source available for frame " + relative)
            continue
        sources[name] = (path, True)
    return sources


def expected_frame_filenames():
    return [name for name, _relative in frame_layout()]


def ensure_directory(path):
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)


# ---------------------------------------------------------------------------
# 1. Textures
# ---------------------------------------------------------------------------
def import_textures(sources):
    """Imports the 20 PNGs and forces pixel-art-correct texture settings."""
    ensure_directory(TEXTURE_DIR)

    tasks = []
    wanted = []

    for filename in expected_frame_filenames():
        entry = sources.get(filename)
        if entry is None:
            continue
        full = entry[0]

        asset_name = "T_Ravager_" + os.path.splitext(filename)[0]
        wanted.append(asset_name)

        task = unreal.AssetImportTask()
        task.set_editor_property("filename", full)
        task.set_editor_property("destination_path", TEXTURE_DIR)
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", False)
        tasks.append(task)

    if not tasks:
        fail("no source frames available at all")
        return {}

    _asset_tools.import_asset_tasks(tasks)

    textures = {}
    for asset_name in wanted:
        path = TEXTURE_DIR + "/" + asset_name
        texture = unreal.EditorAssetLibrary.load_asset(path)
        if texture is None:
            fail("texture failed to import: " + path)
            continue

        configure_pixel_art_texture(texture)
        unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
        textures[asset_name] = texture
        _summary["textures"] += 1

    info("textures ready: {0}".format(len(textures)))
    return textures


def configure_pixel_art_texture(texture):
    """
    Nearest-neighbour, no mips, no block compression.

    Any one of these being wrong is enough to make the whole game look
    blurry or produce dirty alpha edges, so they are all set explicitly
    rather than trusted to the import defaults.
    """
    set_prop(texture, "filter", unreal.TextureFilter.TF_NEAREST)
    set_prop(texture, "mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    set_prop(texture, "compression_settings",
             unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    set_prop(texture, "lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
    set_prop(texture, "srgb", True)
    set_prop(texture, "never_stream", True)
    set_prop(texture, "compression_no_alpha", False)


# ---------------------------------------------------------------------------
# 2. Sprites
# ---------------------------------------------------------------------------
def create_sprites(textures):
    """
    One PaperSprite per texture, all sharing the same feet pivot.

    The pivot is the single most important value here: every frame uses
    (64, 120) in texture space, so switching flipbook or direction cannot
    shift the character vertically by even one pixel.
    """
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

        # The factory cannot be pre-configured from Python (its fields are
        # plain C++ members, not UPROPERTYs), so the source rectangle is set
        # here instead. Setting these fires PostEditChangeProperty, which is
        # what rebuilds the sprite's render geometry.
        set_prop(sprite, "source_texture", texture)
        set_prop(sprite, "source_uv", unreal.Vector2D(0.0, 0.0))
        set_prop(sprite, "source_dimension",
                 unreal.Vector2D(float(FRAME_WIDTH), float(FRAME_HEIGHT)))

        set_prop(sprite, "pixels_per_unreal_unit", PIXELS_PER_UNREAL_UNIT)
        set_prop(sprite, "pivot_mode", unreal.SpritePivotMode.CUSTOM)
        set_prop(sprite, "custom_pivot_point", unreal.Vector2D(PIVOT_X, PIVOT_Y))
        set_prop(sprite, "snap_pivot_to_pixel_grid", True)

        # Characters never need per-sprite physics; the capsule is the
        # gameplay footprint.
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

        path = FLIPBOOK_DIR + "/" + name
        flipbook = unreal.EditorAssetLibrary.load_asset(path)
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

    for direction in DIRECTIONS:
        name = "FB_Ravager_Idle_" + direction
        flipbook = build(name, ["SPR_Ravager_Idle_" + direction], IDLE_FPS)
        if flipbook:
            flipbooks[name] = flipbook

    # Walk and attack are built the same way: eight sprites, in frame order,
    # at the animation's own FPS. Frame order is the file order, which the
    # extraction step guaranteed matches the intended cycle
    # (contact -> passing -> ... -> loop preparation for walk,
    #  ready -> wind-up -> impact -> recovery -> ready for attack).
    for anim, count, fps in (("Walk", WALK_FRAME_COUNT, WALK_FPS),
                             ("Attack", ATTACK_FRAME_COUNT, ATTACK_FPS)):
        for direction in DIRECTIONS:
            name = "FB_Ravager_{0}_{1}".format(anim, direction)
            sprite_names = [
                "SPR_Ravager_{0}_{1}_{2:02d}".format(anim, direction, index)
                for index in range(1, count + 1)
            ]
            flipbook = build(name, sprite_names, fps)
            if flipbook:
                flipbooks[name] = flipbook

    info("flipbooks ready: {0}".format(len(flipbooks)))
    return flipbooks


# ---------------------------------------------------------------------------
# 4. Enhanced Input
# ---------------------------------------------------------------------------
def create_input_assets():
    """
    IA_Move as a single Axis2D action, plus a mapping context.

    Using one 2D action (rather than two 1D axes) is what allows a gamepad
    stick to be added as a single extra mapping later with no code change -
    the stick already produces a 2D value.
    """
    ensure_directory(INPUT_DIR)

    data_asset_factory = unreal.DataAssetFactory()

    # ---- IA_Move ----------------------------------------------------------
    action_path = INPUT_DIR + "/IA_Move"
    move_action = unreal.EditorAssetLibrary.load_asset(action_path)
    if move_action is None:
        set_prop(data_asset_factory, "data_asset_class", unreal.InputAction)
        move_action = _asset_tools.create_asset(
            "IA_Move", INPUT_DIR, unreal.InputAction, data_asset_factory)

    if move_action is None:
        fail("could not create IA_Move")
        return None, None, None

    set_prop(move_action, "value_type", unreal.InputActionValueType.AXIS2D)
    unreal.EditorAssetLibrary.save_loaded_asset(move_action, only_if_is_dirty=False)
    _summary["input"] += 1

    # ---- IA_Attack --------------------------------------------------------
    attack_path = INPUT_DIR + "/IA_Attack"
    attack_action = unreal.EditorAssetLibrary.load_asset(attack_path)
    if attack_action is None:
        set_prop(data_asset_factory, "data_asset_class", unreal.InputAction)
        attack_action = _asset_tools.create_asset(
            "IA_Attack", INPUT_DIR, unreal.InputAction, data_asset_factory)

    if attack_action is None:
        fail("could not create IA_Attack")
        return None, None, None

    # Digital, not Axis2D: an attack is a press, not a magnitude.
    set_prop(attack_action, "value_type", unreal.InputActionValueType.BOOLEAN)
    unreal.EditorAssetLibrary.save_loaded_asset(attack_action, only_if_is_dirty=False)
    _summary["input"] += 1

    # ---- IMC_PTK_Default --------------------------------------------------
    context_path = INPUT_DIR + "/IMC_PTK_Default"
    context = unreal.EditorAssetLibrary.load_asset(context_path)
    if context is None:
        set_prop(data_asset_factory, "data_asset_class", unreal.InputMappingContext)
        context = _asset_tools.create_asset(
            "IMC_PTK_Default", INPUT_DIR, unreal.InputMappingContext, data_asset_factory)

    if context is None:
        fail("could not create IMC_PTK_Default")
        return move_action, attack_action, None

    mappings = build_move_mappings(move_action, context)
    mappings += build_attack_mappings(attack_action, context)

    # UE 5.7 moved the mapping list into the DefaultKeyMappings struct and
    # deprecated the flat array. Try the current layout, fall back to legacy.
    applied = False
    try:
        data = unreal.InputMappingContextMappingData()
        data.set_editor_property("mappings", mappings)
        context.set_editor_property("default_key_mappings", data)
        applied = True
    except Exception as exc:  # noqa: BLE001
        warn("default_key_mappings unavailable ({0}); trying legacy layout".format(exc))

    if not applied:
        applied = set_prop(context, "mappings", mappings)

    if not applied:
        fail("could not write key mappings into IMC_PTK_Default - add them by hand")

    unreal.EditorAssetLibrary.save_loaded_asset(context, only_if_is_dirty=False)
    _summary["input"] += 1

    info("input assets ready (IA_Move, IA_Attack, IMC_PTK_Default)")
    return move_action, attack_action, context


def build_attack_mappings(attack_action, owner):
    """
    Space bar, with the left mouse button as a second binding.

    Space is the primary: it is the one clear default, it works with the left
    hand already on WASD, and it does not depend on where the cursor is. The
    mouse button is added because it costs nothing here - both keys emit the
    same digital value into the same action, so there is no extra state, no
    modifiers and no ordering to get wrong.
    """
    def make_key(name):
        try:
            return unreal.Key(key_name=name)
        except Exception:  # noqa: BLE001
            key = unreal.Key()
            key.set_editor_property("key_name", name)
            return key

    mappings = []
    for key_name in ("SpaceBar", "LeftMouseButton"):
        mapping = unreal.EnhancedActionKeyMapping()
        mapping.set_editor_property("action", attack_action)
        mapping.set_editor_property("key", make_key(key_name))
        mappings.append(mapping)
    return mappings


def build_move_mappings(move_action, owner):
    """
    W = Y+   S = Y-   A = X-   D = X+   plus the gamepad left stick.

    A digital key emits 1.0 on X. Swizzling YXZ moves that onto Y, and
    Negate flips the sign, which is how four keys drive one 2D action.
    Modifiers apply in list order, so Swizzle must come before Negate.

    CRITICAL: each modifier must be created with `owner` (the mapping context
    asset) as its Outer.

    Calling `unreal.InputModifierSwizzleAxis()` instead produces a TRANSIENT
    object. It assigns fine and even reads back correctly in the same session,
    but it cannot be serialised into the asset package - so after saving, every
    modifier slot reloads as null. The mappings then deliver the raw key value
    (+1, 0) for W, A, S and D alike, and every direction moves the same way.
    That is exactly the bug this line prevents.
    """
    def swizzle_yxz():
        modifier = unreal.new_object(unreal.InputModifierSwizzleAxis, owner)
        modifier.set_editor_property("order", unreal.InputAxisSwizzle.YXZ)
        return modifier

    def negate():
        return unreal.new_object(unreal.InputModifierNegate, owner)

    def make_key(name):
        """FKey cannot be built positionally from Python; go via its property."""
        try:
            return unreal.Key(key_name=name)
        except Exception:  # noqa: BLE001
            key = unreal.Key()
            key.set_editor_property("key_name", name)
            return key

    plan = [
        ("W", [swizzle_yxz()]),
        ("S", [swizzle_yxz(), negate()]),
        ("A", [negate()]),
        ("D", []),
        # Analog stick: already a 2D value, so it needs no modifiers at all.
        ("Gamepad_Left2D", []),
    ]

    mappings = []
    for key_name, modifiers in plan:
        mapping = unreal.EnhancedActionKeyMapping()
        mapping.set_editor_property("action", move_action)
        mapping.set_editor_property("key", make_key(key_name))
        if modifiers:
            mapping.set_editor_property("modifiers", modifiers)
        mappings.append(mapping)

    return mappings


# ---------------------------------------------------------------------------
# 5. Ravager Blueprint (requires the compiled C++ module)
# ---------------------------------------------------------------------------
def create_ravager_blueprint(flipbooks, move_action, attack_action, context):
    guard_class = getattr(unreal, "PTKGuardCharacter", None)
    if guard_class is None:
        warn(
            "APTKGuardCharacter is not loaded, so BP_Ravager was skipped. "
            "Compile the C++ module and run this script again."
        )
        return None

    ensure_directory(BLUEPRINT_DIR)

    path = BLUEPRINT_DIR + "/BP_Ravager"
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        factory = unreal.BlueprintFactory()
        set_prop(factory, "parent_class", guard_class)
        blueprint = _asset_tools.create_asset(
            "BP_Ravager", BLUEPRINT_DIR, unreal.Blueprint, factory)

    if blueprint is None:
        fail("could not create BP_Ravager")
        return None

    cdo = unreal.get_default_object(blueprint.generated_class())
    if cdo is None:
        fail("could not reach the BP_Ravager class defaults")
        return blueprint

    def directional(prefix):
        value = unreal.PTKDirectionalFlipbooks()
        for direction in DIRECTIONS:
            value.set_editor_property(
                direction.lower(), flipbooks.get(prefix + direction))
        return value

    set_prop(cdo, "idle_flipbooks", directional("FB_Ravager_Idle_"))
    set_prop(cdo, "walk_flipbooks", directional("FB_Ravager_Walk_"))
    set_prop(cdo, "attack_flipbooks", directional("FB_Ravager_Attack_"))

    if move_action:
        set_prop(cdo, "move_action", move_action)
    if attack_action:
        set_prop(cdo, "attack_action", attack_action)
    if context:
        set_prop(cdo, "default_mapping_context", context)

    set_prop(cdo, "guard_id", "Ravager")
    set_prop(cdo, "guard_display_name", unreal.Text("Ravager"))

    # Ravager is a heavy front-line guard: a little slower than baseline.
    set_prop(cdo, "max_move_speed", 240.0)
    set_prop(cdo, "collision_radius", 14.0)
    set_prop(cdo, "collision_half_height", 14.0)
    set_prop(cdo, "default_facing_direction", unreal.PTKFacingDirection.DOWN)

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:  # noqa: BLE001
        warn("BP_Ravager did not compile from script: {0}".format(exc))

    unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
    _summary["blueprint"] += 1
    info("BP_Ravager ready")
    return blueprint


# ---------------------------------------------------------------------------
# 6. Test level
# ---------------------------------------------------------------------------
def create_test_level():
    """
    A deliberately plain arena: open floor, a wall perimeter and a few
    obstacles. Its only job is to prove movement, animation and collision.
    The real map is out of scope for Phase 1.
    """
    ensure_directory(MAPS_DIR)

    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    if level_subsystem is None or actor_subsystem is None:
        fail("editor subsystems unavailable - cannot build the test level")
        return False

    level_subsystem.new_level(LEVEL_PATH)

    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH)
    if cube is None:
        fail("engine cube mesh not found at " + CUBE_MESH)
        return False

    def block(name, location, scale, blocking=True):
        actor = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(*location), unreal.Rotator(0, 0, 0))
        if actor is None:
            warn("failed to spawn " + name)
            return None
        actor.set_actor_label(name)
        actor.set_actor_scale3d(unreal.Vector(*scale))
        component = actor.static_mesh_component
        component.set_static_mesh(cube)
        component.set_mobility(unreal.ComponentMobility.STATIC)
        if not blocking:
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        return actor

    # The camera sits on the -Y side looking toward +Y (see CameraBoomYaw in
    # PTKTopDownCharacter.cpp), so "behind the play plane" means MORE POSITIVE Y.
    # Putting the backdrop on the camera's side would place it between the
    # camera and every character and black out the entire view.
    block("Backdrop", (0.0, 300.0, 0.0), (20.0, 0.2, 13.0), blocking=False)

    # Arena perimeter. Walls are kept thin in Y so they occupy roughly the same
    # depth slice as the characters - a 100 uu thick wall would poke closer to
    # the camera than a character's depth-sort offset and wrongly draw in front.
    half_width = 700.0
    half_height = 450.0
    thickness = 0.5
    depth = 0.2

    block("Wall_Left", (-half_width, 0.0, 0.0), (thickness, depth, half_height / 50.0))
    block("Wall_Right", (half_width, 0.0, 0.0), (thickness, depth, half_height / 50.0))
    block("Wall_Bottom", (0.0, 0.0, -half_height), (half_width / 50.0, depth, thickness))
    block("Wall_Top", (0.0, 0.0, half_height), (half_width / 50.0, depth, thickness))

    # A few obstacles to walk around and slide along.
    block("Obstacle_A", (-300.0, 0.0, 150.0), (1.5, depth, 1.5))
    block("Obstacle_B", (250.0, 0.0, -100.0), (2.0, depth, 1.0))
    block("Obstacle_C", (0.0, 0.0, 250.0), (1.0, depth, 1.0))

    # Spawn point at the origin of the play plane.
    start = actor_subsystem.spawn_actor_from_class(
        unreal.PlayerStart, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0, 0, 0))
    if start:
        start.set_actor_label("PlayerStart")

    # Sprites are unlit, but the cube meshes are not.
    # unreal.Rotator takes (roll, pitch, yaw). Yaw 90 aims the light along +Y,
    # i.e. from the camera side into the scene, pitched down 45 degrees. Lighting
    # from the far side would leave every camera-facing surface in shadow.
    light = actor_subsystem.spawn_actor_from_class(
        unreal.DirectionalLight, unreal.Vector(0.0, -500.0, 500.0),
        unreal.Rotator(0.0, -45.0, 90.0))
    if light:
        light.set_actor_label("DirectionalLight")
        light.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)

    sky = actor_subsystem.spawn_actor_from_class(
        unreal.SkyLight, unreal.Vector(0.0, 0.0, 200.0), unreal.Rotator(0, 0, 0))
    if sky:
        sky.set_actor_label("SkyLight")
        sky.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)

    level_subsystem.save_current_level()
    _summary["level"] += 1
    info("test level ready: " + LEVEL_PATH)
    return True


# ---------------------------------------------------------------------------
# 7. Verification - read the assets back and prove they are correct
# ---------------------------------------------------------------------------
def verify_assets():
    """
    Re-loads what was written and checks the properties that actually matter.

    Generating an asset is not the same as generating a *correct* asset, and
    a wrong pivot or a stray bilinear filter is invisible until it ruins the
    look of the game. This is the check that makes the summary trustworthy.
    """
    info("-" * 62)
    info("VERIFICATION")
    info("-" * 62)

    ok = True

    # ---- textures ---------------------------------------------------------
    bad_textures = []
    for name in ["T_Ravager_" + os.path.splitext(n)[0] for n in expected_frame_filenames()]:
        texture = unreal.EditorAssetLibrary.load_asset(TEXTURE_DIR + "/" + name)
        if texture is None:
            bad_textures.append(name + " (missing)")
            continue
        problems = []
        if texture.get_editor_property("filter") != unreal.TextureFilter.TF_NEAREST:
            problems.append("filter")
        if texture.get_editor_property("mip_gen_settings") != \
                unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS:
            problems.append("mips")
        if texture.get_editor_property("compression_settings") != \
                unreal.TextureCompressionSettings.TC_EDITOR_ICON:
            problems.append("compression")
        if not texture.get_editor_property("srgb"):
            problems.append("srgb")
        if problems:
            bad_textures.append("{0} ({1})".format(name, "+".join(problems)))

    if bad_textures:
        ok = False
        fail("textures with wrong import settings: " + ", ".join(bad_textures[:5]))
    else:
        info("PASS  {0}/{0} textures: Nearest filter, no mips, uncompressed, sRGB"
             .format(len(expected_frame_filenames())))

    # ---- sprites ----------------------------------------------------------
    pivots = set()
    ppus = set()
    dims = set()
    missing_sprites = []

    for name in ["SPR_Ravager_" + os.path.splitext(n)[0] for n in expected_frame_filenames()]:
        sprite = unreal.EditorAssetLibrary.load_asset(SPRITE_DIR + "/" + name)
        if sprite is None:
            missing_sprites.append(name)
            continue
        pivot = sprite.get_editor_property("custom_pivot_point")
        mode = sprite.get_editor_property("pivot_mode")
        pivots.add((round(pivot.x, 3), round(pivot.y, 3), str(mode)))
        ppus.add(round(sprite.get_editor_property("pixels_per_unreal_unit"), 4))
        dimension = sprite.get_editor_property("source_dimension")
        dims.add((round(dimension.x), round(dimension.y)))

    if missing_sprites:
        ok = False
        fail("missing sprites: " + ", ".join(missing_sprites[:5]))

    if len(pivots) == 1:
        entry = next(iter(pivots))
        if entry[0] == PIVOT_X and entry[1] == PIVOT_Y:
            info("PASS  {0}/{0} sprites share the feet pivot ({1}, {2}) [{3}]".format(
                len(expected_frame_filenames()), entry[0], entry[1], entry[2]))
        else:
            ok = False
            fail("all sprites agree but the pivot is {0}, expected ({1}, {2})".format(
                entry, PIVOT_X, PIVOT_Y))
    elif pivots:
        ok = False
        fail("sprites disagree about the pivot - the character WILL jump: {0}".format(pivots))

    if ppus == {PIXELS_PER_UNREAL_UNIT}:
        info("PASS  {0}/{0} sprites at {1} pixel(s) per Unreal unit".format(
            len(expected_frame_filenames()), PIXELS_PER_UNREAL_UNIT))
    else:
        ok = False
        fail("inconsistent pixels-per-unit across sprites: {0}".format(ppus))

    if dims == {(FRAME_WIDTH, FRAME_HEIGHT)}:
        info("PASS  {0}/{0} sprites are {1}x{2}".format(
            len(expected_frame_filenames()), FRAME_WIDTH, FRAME_HEIGHT))
    else:
        ok = False
        fail("inconsistent sprite source dimensions: {0}".format(dims))

    # ---- flipbooks --------------------------------------------------------
    # Each animation is checked against its OWN frame count and FPS. Walk and
    # attack deliberately run at different rates, so a single expected FPS
    # would be wrong for one of them.
    expected_specs = {
        "Idle": (1, IDLE_FPS),
        "Walk": (WALK_FRAME_COUNT, WALK_FPS),
        "Attack": (ATTACK_FRAME_COUNT, ATTACK_FPS),
    }
    wrong_order = []

    for state, (count, expected_fps) in expected_specs.items():
        for direction in DIRECTIONS:
            name = "FB_Ravager_{0}_{1}".format(state, direction)
            flipbook = unreal.EditorAssetLibrary.load_asset(FLIPBOOK_DIR + "/" + name)
            if flipbook is None:
                ok = False
                fail("missing flipbook " + name)
                continue
            frames = flipbook.get_editor_property("key_frames")
            fps = flipbook.get_editor_property("frames_per_second")
            if len(frames) != count:
                ok = False
                fail("{0} has {1} key frames, expected {2}".format(name, len(frames), count))
            if abs(fps - expected_fps) > 0.001:
                ok = False
                fail("{0} runs at {1} FPS, expected {2}".format(name, fps, expected_fps))

            for index, frame in enumerate(frames):
                sprite = frame.get_editor_property("sprite")
                if sprite is None:
                    ok = False
                    fail(name + " has an empty key frame")
                    continue
                # Frame order is the whole animation. A flipbook holding the
                # right eight sprites in the wrong sequence still passes a
                # count check and still looks broken on screen, so the sprite
                # name is matched against the slot it occupies.
                if state == "Idle":
                    expected_sprite = "SPR_Ravager_Idle_" + direction
                else:
                    expected_sprite = "SPR_Ravager_{0}_{1}_{2:02d}".format(
                        state, direction, index + 1)
                if sprite.get_name() != expected_sprite:
                    wrong_order.append("{0}[{1}] = {2}, expected {3}".format(
                        name, index, sprite.get_name(), expected_sprite))

    if wrong_order:
        ok = False
        fail("flipbook frames are out of order: " + ", ".join(wrong_order[:5]))
    else:
        info("PASS  every flipbook frame sits in its intended slot")

    if ok:
        info("PASS  12/12 flipbooks: 4 idle (1 frame @ {0} FPS), 4 walk ({1} @ {2} FPS), "
             "4 attack ({3} @ {4} FPS)".format(
                 IDLE_FPS, WALK_FRAME_COUNT, WALK_FPS, ATTACK_FRAME_COUNT, ATTACK_FPS))

    # ---- input ------------------------------------------------------------
    action = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/IA_Move")
    if action is None:
        ok = False
        fail("IA_Move missing")
    else:
        value_type = action.get_editor_property("value_type")
        if value_type == unreal.InputActionValueType.AXIS2D:
            info("PASS  IA_Move is an Axis2D action")
        else:
            ok = False
            fail("IA_Move is {0}, expected Axis2D".format(value_type))

    attack = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/IA_Attack")
    if attack is None:
        ok = False
        fail("IA_Attack missing")
    else:
        value_type = attack.get_editor_property("value_type")
        if value_type == unreal.InputActionValueType.BOOLEAN:
            info("PASS  IA_Attack is a digital (bool) action")
        else:
            ok = False
            fail("IA_Attack is {0}, expected Boolean".format(value_type))

    context = unreal.EditorAssetLibrary.load_asset(INPUT_DIR + "/IMC_PTK_Default")
    if context is None:
        ok = False
        fail("IMC_PTK_Default missing")
    else:
        mappings = []
        try:
            data = context.get_editor_property("default_key_mappings")
            mappings = data.get_editor_property("mappings")
        except Exception:  # noqa: BLE001
            try:
                mappings = context.get_editor_property("mappings")
            except Exception:  # noqa: BLE001
                mappings = []

        keys = [str(m.get_editor_property("key").get_editor_property("key_name"))
                for m in mappings]
        needed = ["W", "A", "S", "D", "SpaceBar", "LeftMouseButton"]
        if all(k in keys for k in needed):
            info("PASS  IMC_PTK_Default maps {0}".format(", ".join(keys)))
        else:
            ok = False
            fail("IMC_PTK_Default is missing WASD; it has: {0}".format(keys))

        # Resolve each key the way Enhanced Input will at runtime: a digital
        # press is (1,0), then the saved modifiers are applied in order.
        #
        # This check exists because modifiers created without a proper Outer
        # silently reload as null, which makes every key produce (+1, 0) and
        # every direction move the same way on screen.
        expected = {"W": (0.0, 1.0), "S": (0.0, -1.0),
                    "A": (-1.0, 0.0), "D": (1.0, 0.0)}
        for mapping in mappings:
            key_obj = mapping.get_editor_property("key")
            key_name = str(key_obj.get_editor_property("key_name")) if key_obj else "?"
            if key_name not in expected:
                continue

            try:
                modifiers = mapping.get_editor_property("modifiers")
            except Exception:  # noqa: BLE001
                modifiers = []

            if any(m is None for m in modifiers):
                ok = False
                fail("IMC_PTK_Default key {0}: a modifier reloaded as NULL - "
                     "modifiers must be created with unreal.new_object(cls, context)"
                     .format(key_name))
                continue

            x, y = 1.0, 0.0
            for modifier in modifiers:
                cls = modifier.get_class().get_name()
                if cls == "InputModifierSwizzleAxis":
                    x, y = y, x
                elif cls == "InputModifierNegate":
                    x, y = -x, -y

            want = expected[key_name]
            if abs(x - want[0]) < 0.001 and abs(y - want[1]) < 0.001:
                info("PASS  key {0} resolves to ({1:+.0f}, {2:+.0f})".format(key_name, x, y))
            else:
                ok = False
                fail("key {0} resolves to ({1:+.0f}, {2:+.0f}), expected ({3:+.0f}, {4:+.0f})"
                     .format(key_name, x, y, want[0], want[1]))

    # ---- level ------------------------------------------------------------
    if unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PATH):
        info("PASS  test level exists at " + LEVEL_PATH)
    else:
        ok = False
        fail("test level missing at " + LEVEL_PATH)

    info("-" * 62)
    info("VERIFICATION: " + ("ALL CHECKS PASSED" if ok else "FAILURES ABOVE"))
    info("-" * 62)
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    info("=" * 62)
    info("Protect the King - 2D : Phase 1 asset generation")
    info("=" * 62)

    sources = resolve_frame_sources()
    final_frames = sorted(n for n, (_p, f) in sources.items() if f)
    temp_frames = sorted(n for n, (_p, f) in sources.items() if not f)

    info("frame sources: {0} FINAL, {1} TEMPORARY".format(
        len(final_frames), len(temp_frames)))
    for name in final_frames:
        info("   FINAL  " + name)
    for name in temp_frames:
        info("   TEMP   " + name)

    if not sources:
        fail("no source frames could be resolved")
        return

    textures = import_textures(sources)
    sprites = create_sprites(textures)
    flipbooks = create_flipbooks(sprites)
    move_action, attack_action, context = create_input_assets()
    create_ravager_blueprint(flipbooks, move_action, attack_action, context)
    create_test_level()

    unreal.EditorAssetLibrary.save_directory("/Game/PTK", only_if_is_dirty=False,
                                             recursive=True)

    verify_assets()

    info("=" * 62)
    info("textures  : {0}".format(_summary["textures"]))
    info("sprites   : {0}".format(_summary["sprites"]))
    info("flipbooks : {0}".format(_summary["flipbooks"]))
    info("input     : {0}".format(_summary["input"]))
    info("level     : {0}".format(_summary["level"]))
    info("blueprint : {0}".format(_summary["blueprint"]))
    info("warnings  : {0}".format(len(_summary["warnings"])))
    info("errors    : {0}".format(len(_summary["errors"])))

    for message in _summary["errors"]:
        unreal.log_error("[PTK] ERROR: " + message)

    if temp_frames:
        info("")
        info("REMINDER: {0} of 20 frames are still TEMPORARY placeholders.".format(
            len(temp_frames)))
        info("They are the WALK cycle. The turnaround sheet only supplies idle poses,")
        info("so real walk frames must be authored separately.")
        info("Drop them into ArtSource/Characters/Guards/Ravager/Frames and re-run.")

    info("=" * 62)


main()
