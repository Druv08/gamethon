"""
Protect the King - 2D
Unreal Editor Python script: puts all five guards on the field, one player-
driven and four AI-driven.

RUN THIS INSIDE THE UNREAL EDITOR:
    UnrealEditor-Cmd.exe <ProjectDir>/ProtectTheKing2D.uproject ^
        -run=pythonscript -script="<ProjectDir>/Tools/PTK_SetupGuardPosts.py"

What it does
------------
1. Gives every guard Blueprint APTKGuardAIController and AutoPossessAI =
   PlacedInWorld.
2. Places Aegis, Wraith, Reaver and Sentinel in L_PTK_TestGround at four
   separated posts, and saves the map.

Re-running is safe: previously placed guards are removed first, so the level
never accumulates duplicates.


WHY PlacedInWorld AND NOT PlacedInWorldOrSpawned
------------------------------------------------
This one setting is what decides who the player is, and it does it without a
single special case.

The player's Ravager is SPAWNED by the game mode from DefaultPawnClass at the
PlayerStart, and is then possessed by the PlayerController. The other four are
PLACED in the level. So "placed guards get an AI controller, spawned ones do
not" resolves to exactly: four AI guards, one player guard.

Using PlacedInWorldOrSpawned would hand the player's own Ravager an AI
controller a moment before the PlayerController takes it - a race whose only
possible outcomes are a wasted controller or a guard that briefly walks off on
its own. A pawn has one controller, so the two would never coexist, but there
is no reason to create the fight in the first place.

Ravager still gets the AIControllerClass. He is never auto-possessed by it, but
guard switching will need to hand him back to the AI when the player moves on,
and it should not have to go looking for which class to use.


WHERE THE POSTS ARE
-------------------
The arena is world XZ: screen-right is -X, screen-up is +Z. The swarm spawner
rings the origin at radius 240 and the King stands at (-480, 0, 240), which is
up and to the screen-right.

    Aegis     ( 170, 0,    0)   the tank, holding the near flank
    Reaver    (   0, 0, -170)   the assassin, holding the low flank
    Wraith    (-220, 0,  120)   archer, further back toward the King
    Sentinel  (-220, 0, -120)   mage, likewise

Nearest neighbours are 240 units apart and nobody is within 170 of the
PlayerStart, so nothing spawns inside anything else. The two ranged guards sit
behind the melee pair and nearer the King, which is where a bow and a staff
belong - and it means their longer reach is doing the work rather than their
feet.
"""

import unreal


LEVEL = "/Game/PTK/Maps/L_PTK_TestGround"
GUARD_ROOT = "/Game/PTK/Characters/Guards"

# Every guard gets the controller class; only the placed four are auto-possessed.
ALL_GUARDS = ["Ravager", "Aegis", "Wraith", "Reaver", "Sentinel"]

# (guard, x, y, z) - see the module docstring for why these four points.
POSTS = [
    ("Aegis",     170.0, 0.0,    0.0),
    ("Reaver",      0.0, 0.0, -170.0),
    ("Wraith",   -220.0, 0.0,  120.0),
    ("Sentinel", -220.0, 0.0, -120.0),
]

# Labels are how re-running finds and clears what it placed last time.
LABEL_PREFIX = "GuardPost_"

_summary = {"blueprints": 0, "placed": 0, "removed": 0, "warnings": [], "errors": []}


def info(message):
    unreal.log("[PTK] " + message)


def warn(message):
    _summary["warnings"].append(message)
    unreal.log_warning("[PTK] " + message)


def fail(message):
    _summary["errors"].append(message)
    unreal.log_error("[PTK] " + message)


def guard_blueprint(name):
    return unreal.EditorAssetLibrary.load_asset(
        "{0}/{1}/Blueprints/BP_{1}".format(GUARD_ROOT, name))


# ---------------------------------------------------------------------------
# 1. Controller class on every guard
# ---------------------------------------------------------------------------
def configure_controllers():
    ai_class = getattr(unreal, "PTKGuardAIController", None)
    if ai_class is None:
        fail("APTKGuardAIController is not loaded - compile the C++ module first")
        return False

    for name in ALL_GUARDS:
        blueprint = guard_blueprint(name)
        if blueprint is None:
            fail("missing BP_" + name)
            continue
        cdo = unreal.get_default_object(blueprint.generated_class())
        try:
            cdo.set_editor_property("ai_controller_class", ai_class)
            # PlacedInWorld, deliberately - see the module docstring.
            cdo.set_editor_property("auto_possess_ai",
                                    unreal.AutoPossessAI.PLACED_IN_WORLD)
        except Exception as exc:  # noqa: BLE001
            fail("could not set AI properties on BP_{0}: {1}".format(name, exc))
            continue
        unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
        _summary["blueprints"] += 1
        info("BP_{0}: AIControllerClass = PTKGuardAIController, "
             "AutoPossessAI = PlacedInWorld".format(name))
    return True


# ---------------------------------------------------------------------------
# 2. Place the four AI guards
# ---------------------------------------------------------------------------
def actor_subsystem():
    """EditorActorSubsystem in 5.8; EditorLevelLibrary is the deprecated shim."""
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def all_level_actors():
    return actor_subsystem().get_all_level_actors()


def place_guards():
    unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
    actors = actor_subsystem()

    for actor in all_level_actors():
        if actor.get_actor_label().startswith(LABEL_PREFIX):
            actors.destroy_actor(actor)
            _summary["removed"] += 1
    if _summary["removed"]:
        info("cleared {0} guard(s) from a previous run".format(_summary["removed"]))

    for name, x, y, z in POSTS:
        blueprint = guard_blueprint(name)
        if blueprint is None:
            fail("missing BP_" + name)
            continue
        # The generated CLASS, not the Blueprint asset - spawning the asset
        # itself silently produces nothing.
        actor = actors.spawn_actor_from_class(
            blueprint.generated_class(), unreal.Vector(x, y, z),
            unreal.Rotator(0.0, 0.0, 0.0))
        if actor is None:
            fail("could not place " + name)
            continue
        actor.set_actor_label(LABEL_PREFIX + name)
        _summary["placed"] += 1
        info("placed {0:<9s} at ({1:.0f}, {2:.0f}, {3:.0f})".format(name, x, y, z))

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    info("level saved")


# ---------------------------------------------------------------------------
# 3. Verification
# ---------------------------------------------------------------------------
def verify():
    info("")
    info("-" * 62)
    info("verification")
    ok = True

    for name in ALL_GUARDS:
        blueprint = guard_blueprint(name)
        if blueprint is None:
            ok = False
            continue
        cdo = unreal.get_default_object(blueprint.generated_class())
        controller = cdo.get_editor_property("ai_controller_class")
        possess = cdo.get_editor_property("auto_possess_ai")
        if controller is None or "PTKGuardAIController" not in str(controller):
            ok = False
            fail("BP_{0} has AIControllerClass {1}".format(name, controller))
        if possess != unreal.AutoPossessAI.PLACED_IN_WORLD:
            ok = False
            fail("BP_{0} has AutoPossessAI {1}".format(name, possess))
    if ok:
        info("PASS  all 5 guard Blueprints use PTKGuardAIController, "
             "auto-possessed only when PLACED")

    placed = {}
    for actor in all_level_actors():
        label = actor.get_actor_label()
        if label.startswith(LABEL_PREFIX):
            placed[label[len(LABEL_PREFIX):]] = actor.get_actor_location()

    expected = {name for name, _x, _y, _z in POSTS}
    if set(placed) != expected:
        ok = False
        fail("placed guards are {0}, expected {1}".format(sorted(placed), sorted(expected)))
    else:
        info("PASS  4 AI guards placed: " + ", ".join(sorted(placed)))

    # Nobody stacked on anybody, including the PlayerStart.
    points = list(placed.items()) + [("PlayerStart", unreal.Vector(0.0, 0.0, 0.0))]
    closest = None
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            d = (points[i][1] - points[j][1]).length()
            if closest is None or d < closest[0]:
                closest = (d, points[i][0], points[j][0])
    if closest and closest[0] < 100.0:
        ok = False
        fail("{0} and {1} are only {2:.0f} units apart".format(
            closest[1], closest[2], closest[0]))
    elif closest:
        info("PASS  nothing is stacked - closest pair is {0} and {1} at {2:.0f} units"
             .format(closest[1], closest[2], closest[0]))

    info("-" * 62)
    info("VERIFICATION {0}".format("PASSED" if ok else "FAILED"))
    return ok


def main():
    info("=" * 62)
    info("Guard posts: 1 player guard + 4 AI guards")
    info("=" * 62)
    if configure_controllers():
        place_guards()
        verify()
    info("=" * 62)
    for key in ("blueprints", "placed", "removed"):
        info("{0:<11}: {1}".format(key, _summary[key]))
    info("{0:<11}: {1}".format("warnings", len(_summary["warnings"])))
    info("{0:<11}: {1}".format("errors", len(_summary["errors"])))
    info("=" * 62)


main()
