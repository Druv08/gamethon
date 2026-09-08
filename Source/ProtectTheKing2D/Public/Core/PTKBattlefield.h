// Protect the King - 2D. The playable map: its extent, its roads and its objectives.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PTKBattlefield.generated.h"

class APTKGuardBase;
class UPTKAnalyticsSubsystem;
class UPTKAdaptiveDirector;
class APTKGuardCharacter;
class APTKKingCharacter;
class APTKSpawnPortal;

/**
 * One junction or destination on the road network.
 *
 * Authored in NORMALISED map space (0..1 across the artwork, origin top-left)
 * rather than in world units, because that is the space the map PNG was drawn
 * in. Re-scaling the battlefield then moves every node with the artwork instead
 * of silently leaving the lanes behind on the old grid.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKLaneNode
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	FName Id = NAME_None;

	/** 0..1 across the map artwork, origin top-left, +V downward. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	FVector2D Normalised = FVector2D::ZeroVector;

	/** Ids this node has a road to. Edges are undirected - listing one side is enough. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	TArray<FName> Links;
};

/**
 * One authored route from a spawn portal to the core.
 *
 * A route is the unit of lane assignment: an enemy is given one when it spawns
 * and walks it node by node for its whole life. That is what makes "stay on the
 * trail" a property of the enemy rather than a re-derived guess - re-solving the
 * shortest path every frame from wherever the enemy currently stands, which is
 * what the first implementation did, lets a crowd drift off the road and then
 * cheerfully re-route across the terrain it has drifted into.
 *
 * Each route deliberately passes exactly one guard base, so assigning enemies
 * round-robin across routes spreads pressure over the whole map instead of
 * letting every horde converge on whichever defender happens to be nearest.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKLaneRoute
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	FName Id = NAME_None;

	/** Which portal this route leaves from. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	FName PortalId = NAME_None;

	/** The guard base this route runs through. Informational, for warnings. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	FName BaseId = NAME_None;

	/** Ordered node ids, portal first and KING last. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Lane")
	TArray<FName> Nodes;
};

/**
 * APTKBattlefield
 * ===============
 * The single source of truth for "where is the map, and what counts as a road".
 *
 * Exactly one of these is placed in the gameplay level. Everything that needs to
 * reason about map space - the camera clamp, the minimap, the spawner, enemy
 * pathing - asks this actor rather than carrying its own copy of the dimensions.
 * That is the whole reason it exists: the map size appears in one place, so
 * re-scaling the battlefield cannot leave the minimap drawing one size while the
 * camera clamps to another.
 *
 *
 * MAP SPACE AND WORLD SPACE
 * -------------------------
 * The artwork is 1672x941 and is authored top-left origin, +V down. The play
 * plane is world XZ with screen-right = -X and screen-up = +Z (see
 * APTKTopDownCharacter). Those two disagree on the direction of BOTH axes, so
 * every conversion goes through NormalisedToWorld / WorldToNormalised and
 * nothing open-codes the sign flips.
 *
 *
 * WHY A WAYPOINT GRAPH AND NOT A NAVMESH
 * --------------------------------------
 * The requirement is that enemies use the painted roads and do not cut through
 * the forest. A navmesh would have to be carved to match artwork it knows
 * nothing about, and every gap in that carving becomes a shortcut. A graph
 * authored from the same normalised coordinates as the artwork cannot drift from
 * it, is trivially inspectable, and is small enough (about two dozen nodes) that
 * a full Dijkstra costs less than the overlap query it replaces.
 *
 * The graph also answers the targeting question in section 5 of the spec -
 * "nearest by path, not through walls" - with the same data structure, rather
 * than needing a second system.
 *
 *
 * THE OBJECTIVE REGISTRY
 * ----------------------
 * Guards, bases and the King register themselves here as they begin play and
 * unregister as they are destroyed. Enemy targeting then reads a cached array
 * instead of calling GetAllActorsOfClass, which at a few hundred enemies is the
 * difference between a frame and a stutter.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKBattlefield : public AActor
{
	GENERATED_BODY()

public:
	APTKBattlefield();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	/** The one battlefield in this world, or nullptr. Cached after first find. */
	static APTKBattlefield* Get(const UWorld* World);

	// ------------------------------------------------------------------
	// Map extent
	// ------------------------------------------------------------------

	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	float GetMapWidth() const { return MapWorldWidth; }

	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	float GetMapHeight() const { return MapWorldHeight; }

	/** Centre of the map on the play plane. */
	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	FVector GetMapCentre() const { return MapCentre; }

	/** Normalised map coords (0..1, top-left origin) to a point on the play plane. */
	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	FVector NormalisedToWorld(const FVector2D& Normalised) const;

	/** Inverse of NormalisedToWorld. Y (depth) is ignored. */
	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	FVector2D WorldToNormalised(const FVector& World) const;

	/** Clamps a play-plane point inside the map rectangle, less Margin. */
	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	FVector ClampToMap(const FVector& World, float Margin = 0.0f) const;

	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	bool IsInsideMap(const FVector& World, float Margin = 0.0f) const;

	/**
	 * Ortho width that shows CameraVisibleFraction of the map.
	 *
	 * Derived rather than authored so that re-scaling the map cannot leave the
	 * camera showing the wrong share of it - which is the exact failure the
	 * "do not use a random fixed value" instruction is guarding against.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	float GetCameraOrthoWidth() const { return MapWorldWidth * CameraVisibleFraction; }

	UFUNCTION(BlueprintPure, Category = "PTK|Map")
	float GetCameraVisibleFraction() const { return CameraVisibleFraction; }

	// ------------------------------------------------------------------
	// Lanes
	// ------------------------------------------------------------------

	/** World location of a named node, or the map centre if the id is unknown. */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	FVector GetNodeLocation(FName NodeId) const;

	/** Nearest lane node to a play-plane point. NAME_None only when the graph is empty. */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	FName FindNearestNode(const FVector& World) const;

	/**
	 * Road distance between two points, measured through the lane graph.
	 *
	 * Both ends are snapped to their nearest node and the straight run from each
	 * point to its node is added, so two things on the same stretch of road do
	 * not both round to the same node and come out zero apart. Returns a large
	 * value when no route exists.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	float GetPathDistance(const FVector& From, const FVector& To) const;

	/**
	 * The next node to walk toward when travelling From -> To along the roads.
	 *
	 * This is the whole of the enemy's pathing: it re-asks every refresh and
	 * walks at whatever comes back, so a target that moves or dies re-routes on
	 * the next tick without any path invalidation bookkeeping.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	bool GetNextLaneStep(const FVector& From, const FVector& To, FVector& OutStep) const;

	const TArray<FPTKLaneNode>& GetLaneNodes() const { return LaneNodes; }

	// ------------------------------------------------------------------
	// Routes
	// ------------------------------------------------------------------

	/** Every authored route. */
	const TArray<FPTKLaneRoute>& GetRoutes() const { return Routes; }

	/** The route with this id, or nullptr. */
	const FPTKLaneRoute* FindRoute(FName RouteId) const;

	/** Ids of every route leaving a portal. */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	TArray<FName> GetRouteIdsForPortal(FName PortalId) const;

	/** World location of the step-th node on a route. Map centre if out of range. */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	FVector GetRouteStepLocation(FName RouteId, int32 Step) const;

	/** How many nodes a route has. */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	int32 GetRouteLength(FName RouteId) const;

	/**
	 * The run's analytics recorder.
	 *
	 * Exposed here because a world subsystem has no Blueprint or Python
	 * accessor of its own in this engine build, and the battlefield is already
	 * the thing everything else asks about the run.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Analytics")
	UPTKAnalyticsSubsystem* GetAnalytics() const;

	/** The adaptive director. Exposed here for the same reason as GetAnalytics. */
	UFUNCTION(BlueprintPure, Category = "PTK|Analytics")
	UPTKAdaptiveDirector* GetDirector() const;

	// ------------------------------------------------------------------
	// Walkable ground
	// ------------------------------------------------------------------

	/**
	 * True where a guard may stand: on a road, on a platform, or on the core.
	 *
	 * Derived from the lane graph rather than from authored blocking volumes.
	 * The graph was traced onto the painted roads in the first place, so it
	 * already describes exactly the ground the artwork shows as walkable - and
	 * a corridor test is both cheaper and far more forgiving than the few
	 * hundred box volumes it would take to enclose every tree and rock, which
	 * would leave guards wedged in the gaps between them.
	 *
	 * Forest, rock, water, structures and everything outside the map read as
	 * blocked because they are simply not near any road or platform.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Terrain")
	bool IsWalkable(const FVector& World) const;

	/**
	 * Nearest walkable point to somewhere blocked. Recovery aid.
	 *
	 * Used when something ends up off the road anyway - spawned there, shoved
	 * there, or teleported by a test - so it can always get back rather than
	 * being stranded.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Terrain")
	FVector FindNearestWalkable(const FVector& World) const;

	/** Half-width of the walkable corridor along a road. */
	UFUNCTION(BlueprintPure, Category = "PTK|Terrain")
	float GetRoadHalfWidth() const { return RoadHalfWidth; }

	/**
	 * Shortest distance from a point to the route's polyline.
	 *
	 * Measured against the SEGMENTS rather than the nodes, so a point halfway
	 * along a long straight stretch is correctly reported as being on the road
	 * instead of hundreds of units from the nearest junction.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	float DistanceToRoute(FName RouteId, const FVector& World) const;

	/** How far along its route a point is, 0..1. For minimap horde progress. */
	UFUNCTION(BlueprintPure, Category = "PTK|Lane")
	float GetRouteProgress(FName RouteId, const FVector& World) const;

	// ------------------------------------------------------------------
	// Objective registry
	// ------------------------------------------------------------------

	void RegisterGuard(APTKGuardCharacter* Guard);
	void UnregisterGuard(APTKGuardCharacter* Guard);
	void RegisterBase(APTKGuardBase* Base);
	void UnregisterBase(APTKGuardBase* Base);
	void RegisterPortal(APTKSpawnPortal* Portal);

	// C++ only: reflection cannot expose a TObjectPtr array, and these are read
	// in the enemy targeting inner loop where a reflected copy would be paid for
	// on every refresh anyway.
	const TArray<TObjectPtr<APTKGuardCharacter>>& GetGuards() const { return Guards; }
	const TArray<TObjectPtr<APTKGuardBase>>& GetBases() const { return Bases; }
	const TArray<TObjectPtr<APTKSpawnPortal>>& GetPortals() const { return Portals; }

	UFUNCTION(BlueprintPure, Category = "PTK|Objectives")
	APTKKingCharacter* GetKing() const;

	/** The base belonging to a guard id, alive or destroyed, or nullptr. */
	UFUNCTION(BlueprintPure, Category = "PTK|Objectives")
	APTKGuardBase* FindBaseForGuard(FName GuardId) const;

protected:
	/** Fills LaneNodes with the authored road network when none was supplied. */
	void BuildDefaultLanes();

	/** Fills Routes with the eight portal-to-core lanes when none were supplied. */
	void BuildDefaultRoutes();

	/** Ids -> index into LaneNodes, rebuilt whenever the graph changes. */
	void RebuildNodeIndex();

	/** Dijkstra from a node over the whole graph. Costs are world distances. */
	void ComputeDistancesFrom(int32 StartIndex, TArray<float>& OutCost, TArray<int32>& OutPrev) const;

	// ------------------------------------------------------------------
	// Authored map data
	// ------------------------------------------------------------------

	/**
	 * World size of the battlefield, in Unreal units.
	 *
	 * Derived from the artwork: 1672x941 pixels at 3 world units per pixel. The
	 * aspect ratio therefore matches the PNG exactly, which is what stops the
	 * painted roads from drifting away from the lane graph laid over them.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Map", meta = (ClampMin = "100.0"))
	float MapWorldWidth = 5016.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Map", meta = (ClampMin = "100.0"))
	float MapWorldHeight = 2823.0f;

	/** Play-plane centre of the artwork. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Map")
	FVector MapCentre = FVector::ZeroVector;

	/**
	 * Share of the map width the camera shows. The spec asks for 25-35%.
	 *
	 * 0.30 sits in the middle of that band, so a later change to the map size
	 * cannot push it out of range from one end.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Map", meta = (ClampMin = "0.05", ClampMax = "1.0"))
	float CameraVisibleFraction = 0.30f;

	/** The road network. Left empty in the editor, filled by BuildDefaultLanes. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Lane")
	TArray<FPTKLaneNode> LaneNodes;

	/** Portal-to-core lanes. Left empty in the editor, filled by BuildDefaultRoutes. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Lane")
	TArray<FPTKLaneRoute> Routes;

	/**
	 * Half-width of walkable road, in world units.
	 *
	 * The painted roads run about 50 px wide, which is 150 uu at this map's
	 * scale, so 75 would be the literal edge of the artwork. This is set wider
	 * on purpose: a guard is a body with width, and holding it to the exact
	 * painted edge makes the road feel like a tightrope. The extra margin sits
	 * on the roadside verge rather than in the trees.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Terrain", meta = (ClampMin = "10.0"))
	float RoadHalfWidth = 120.0f;

	/** Walkable radius around a guard base platform. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Terrain", meta = (ClampMin = "10.0"))
	float PlatformRadius = 310.0f;

	/** Walkable radius around the King's core, which is a larger structure. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Terrain", meta = (ClampMin = "10.0"))
	float CoreRadius = 400.0f;

private:
	TMap<FName, int32> NodeIndex;

	/** Symmetric adjacency, resolved from Links once so lookups never re-scan. */
	TArray<TArray<int32>> Adjacency;

	UPROPERTY()
	TArray<TObjectPtr<APTKGuardCharacter>> Guards;

	UPROPERTY()
	TArray<TObjectPtr<APTKGuardBase>> Bases;

	UPROPERTY()
	TArray<TObjectPtr<APTKSpawnPortal>> Portals;

	UPROPERTY()
	mutable TObjectPtr<APTKKingCharacter> CachedKing;
};
