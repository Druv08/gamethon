#include "Core/PTKBattlefield.h"

#include "Analytics/PTKAdaptiveDirector.h"
#include "Analytics/PTKAnalyticsSubsystem.h"

#include "Characters/PTKGuardCharacter.h"
#include "Characters/PTKKingCharacter.h"
#include "Core/PTKGuardBase.h"
#include "Core/PTKSpawnPortal.h"
#include "EngineUtils.h"
#include "ProtectTheKing2D.h"

namespace
{
	/** Nothing routable is ever this far apart; used as "unreachable". */
	constexpr float UnreachableCost = 1.0e9f;
}

APTKBattlefield::APTKBattlefield()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

APTKBattlefield* APTKBattlefield::Get(const UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<APTKBattlefield> It(const_cast<UWorld*>(World)); It; ++It)
	{
		return *It;
	}
	return nullptr;
}

void APTKBattlefield::BeginPlay()
{
	Super::BeginPlay();

	if (LaneNodes.Num() == 0)
	{
		BuildDefaultLanes();
	}
	RebuildNodeIndex();
	if (Routes.Num() == 0)
	{
		BuildDefaultRoutes();
	}

	UE_LOG(LogPTK, Log, TEXT("BATTLEFIELD | %.0f x %.0f uu | camera shows %.0f%% (ortho %.0f) | %d lane nodes | %d routes"),
		MapWorldWidth, MapWorldHeight, CameraVisibleFraction * 100.0f,
		GetCameraOrthoWidth(), LaneNodes.Num(), Routes.Num());
}

void APTKBattlefield::EndPlay(const EEndPlayReason::Type Reason)
{
	Guards.Reset();
	Bases.Reset();
	Portals.Reset();
	CachedKing = nullptr;
	Super::EndPlay(Reason);
}

// ---------------------------------------------------------------------------
// Map space
//
// Screen-right is -X and screen-up is +Z, while the artwork runs +U right and
// +V down. Both axes therefore flip, which is exactly why this lives in one
// function instead of being written out at each call site.
// ---------------------------------------------------------------------------

FVector APTKBattlefield::NormalisedToWorld(const FVector2D& Normalised) const
{
	const float X = MapCentre.X - (Normalised.X - 0.5f) * MapWorldWidth;
	const float Z = MapCentre.Z + (0.5f - Normalised.Y) * MapWorldHeight;
	return FVector(X, MapCentre.Y, Z);
}

FVector2D APTKBattlefield::WorldToNormalised(const FVector& World) const
{
	const float U = 0.5f - (World.X - MapCentre.X) / FMath::Max(MapWorldWidth, KINDA_SMALL_NUMBER);
	const float V = 0.5f - (World.Z - MapCentre.Z) / FMath::Max(MapWorldHeight, KINDA_SMALL_NUMBER);
	return FVector2D(U, V);
}

FVector APTKBattlefield::ClampToMap(const FVector& World, float Margin) const
{
	const float HalfW = FMath::Max(MapWorldWidth * 0.5f - Margin, 0.0f);
	const float HalfH = FMath::Max(MapWorldHeight * 0.5f - Margin, 0.0f);
	return FVector(
		FMath::Clamp(World.X, MapCentre.X - HalfW, MapCentre.X + HalfW),
		World.Y,
		FMath::Clamp(World.Z, MapCentre.Z - HalfH, MapCentre.Z + HalfH));
}

bool APTKBattlefield::IsInsideMap(const FVector& World, float Margin) const
{
	const float HalfW = MapWorldWidth * 0.5f - Margin;
	const float HalfH = MapWorldHeight * 0.5f - Margin;
	return FMath::Abs(World.X - MapCentre.X) <= HalfW
		&& FMath::Abs(World.Z - MapCentre.Z) <= HalfH;
}

// ---------------------------------------------------------------------------
// The road network
//
// Read off the supplied map artwork. Coordinates are normalised so they stay
// correct at any map scale; see the header for why they are authored in the
// artwork's own space rather than in world units.
//
//   S_*  enemy spawn portals, one per corner of the outer ring
//   J_*  road junctions
//   B_*  the five guard bases
//   KING the central core
// ---------------------------------------------------------------------------

void APTKBattlefield::BuildDefaultLanes()
{
	auto Node = [this](const TCHAR* Id, float U, float V, std::initializer_list<const TCHAR*> Links)
	{
		FPTKLaneNode New;
		New.Id = FName(Id);
		New.Normalised = FVector2D(U, V);
		for (const TCHAR* Link : Links)
		{
			New.Links.Add(FName(Link));
		}
		LaneNodes.Add(MoveTemp(New));
	};

	// Enemy spawn corners.
	Node(TEXT("S_TL"), 0.085f, 0.330f, { TEXT("J_TL"), TEXT("J_ML") });
	Node(TEXT("S_TR"), 0.915f, 0.330f, { TEXT("J_TR"), TEXT("J_MR") });
	Node(TEXT("S_BL"), 0.093f, 0.790f, { TEXT("J_BL"), TEXT("J_ML") });
	Node(TEXT("S_BR"), 0.912f, 0.790f, { TEXT("J_BR"), TEXT("J_MR") });

	// Outer ring junctions.
	Node(TEXT("J_TL"), 0.200f, 0.230f, { TEXT("B_AEGIS"), TEXT("J_ML") });
	Node(TEXT("J_TR"), 0.800f, 0.230f, { TEXT("B_WRAITH"), TEXT("J_MR") });
	Node(TEXT("J_ML"), 0.175f, 0.560f, { TEXT("B_REAVER"), TEXT("J_BL") });
	Node(TEXT("J_MR"), 0.825f, 0.560f, { TEXT("B_RAVAGER"), TEXT("J_BR") });
	Node(TEXT("J_BL"), 0.230f, 0.800f, { TEXT("B_SENTINEL"), TEXT("J_BOT") });
	Node(TEXT("J_BR"), 0.770f, 0.800f, { TEXT("B_SENTINEL"), TEXT("J_BOT") });
	Node(TEXT("J_TOP"), 0.500f, 0.140f, { TEXT("B_AEGIS"), TEXT("B_WRAITH") });
	Node(TEXT("J_BOT"), 0.500f, 0.925f, { TEXT("B_SENTINEL") });

	// Guard bases sit on the road, so enemies meet them on the way in.
	Node(TEXT("B_AEGIS"), 0.368f, 0.225f, { TEXT("J_KTL") });
	Node(TEXT("B_WRAITH"), 0.632f, 0.222f, { TEXT("J_KTR") });
	Node(TEXT("B_REAVER"), 0.283f, 0.560f, { TEXT("J_KTL"), TEXT("J_KBL") });
	Node(TEXT("B_RAVAGER"), 0.718f, 0.558f, { TEXT("J_KTR"), TEXT("J_KBR") });
	Node(TEXT("B_SENTINEL"), 0.500f, 0.795f, { TEXT("J_KBL"), TEXT("J_KBR") });

	// Inner ring around the core.
	Node(TEXT("J_KTL"), 0.395f, 0.380f, { TEXT("KING"), TEXT("J_KTR"), TEXT("J_KBL") });
	Node(TEXT("J_KTR"), 0.605f, 0.380f, { TEXT("KING"), TEXT("J_KBR") });
	Node(TEXT("J_KBL"), 0.395f, 0.610f, { TEXT("KING"), TEXT("J_KBR") });
	Node(TEXT("J_KBR"), 0.605f, 0.610f, { TEXT("KING") });

	Node(TEXT("KING"), 0.500f, 0.475f, {});
}

// ---------------------------------------------------------------------------
// The eight lanes.
//
// Two out of each corner, and each one passes exactly ONE guard base on its way
// to the core. That is what makes round-robin assignment spread a wave over the
// whole map: eight routes cover all five bases, so a wave drawn across several
// of them cannot pile onto a single defender.
//
// Authored rather than derived. A shortest-path solve would collapse several of
// these onto the same stretch of road - the whole point is that they DIFFER.
// ---------------------------------------------------------------------------

void APTKBattlefield::BuildDefaultRoutes()
{
	auto Route = [this](const TCHAR* Id, const TCHAR* Portal, const TCHAR* Base,
		std::initializer_list<const TCHAR*> Nodes)
	{
		FPTKLaneRoute New;
		New.Id = FName(Id);
		New.PortalId = FName(Portal);
		New.BaseId = FName(Base);
		for (const TCHAR* Node : Nodes)
		{
			if (!NodeIndex.Contains(FName(Node)))
			{
				UE_LOG(LogPTK, Warning, TEXT("BATTLEFIELD | route %s names unknown node %s"), Id, Node);
				continue;
			}
			New.Nodes.Add(FName(Node));
		}
		Routes.Add(MoveTemp(New));
	};

	Route(TEXT("NW_Aegis"), TEXT("NorthWest"), TEXT("Aegis"),
		{ TEXT("S_TL"), TEXT("J_TL"), TEXT("B_AEGIS"), TEXT("J_KTL"), TEXT("KING") });
	Route(TEXT("NW_Reaver"), TEXT("NorthWest"), TEXT("Reaver"),
		{ TEXT("S_TL"), TEXT("J_ML"), TEXT("B_REAVER"), TEXT("J_KBL"), TEXT("KING") });

	Route(TEXT("NE_Wraith"), TEXT("NorthEast"), TEXT("Wraith"),
		{ TEXT("S_TR"), TEXT("J_TR"), TEXT("B_WRAITH"), TEXT("J_KTR"), TEXT("KING") });
	Route(TEXT("NE_Ravager"), TEXT("NorthEast"), TEXT("Ravager"),
		{ TEXT("S_TR"), TEXT("J_MR"), TEXT("B_RAVAGER"), TEXT("J_KBR"), TEXT("KING") });

	Route(TEXT("SW_Reaver"), TEXT("SouthWest"), TEXT("Reaver"),
		{ TEXT("S_BL"), TEXT("J_ML"), TEXT("B_REAVER"), TEXT("J_KTL"), TEXT("KING") });
	Route(TEXT("SW_Sentinel"), TEXT("SouthWest"), TEXT("Sentinel"),
		{ TEXT("S_BL"), TEXT("J_BL"), TEXT("B_SENTINEL"), TEXT("J_KBL"), TEXT("KING") });

	Route(TEXT("SE_Ravager"), TEXT("SouthEast"), TEXT("Ravager"),
		{ TEXT("S_BR"), TEXT("J_MR"), TEXT("B_RAVAGER"), TEXT("J_KBR"), TEXT("KING") });
	Route(TEXT("SE_Sentinel"), TEXT("SouthEast"), TEXT("Sentinel"),
		{ TEXT("S_BR"), TEXT("J_BR"), TEXT("B_SENTINEL"), TEXT("J_KBR"), TEXT("KING") });
}

// ---------------------------------------------------------------------------
// Walkable ground
//
// Everything here works on the XZ play plane and ignores Y. Y is the depth
// axis: characters are shifted along it to sort in front of and behind each
// other, so a guard standing squarely on a road can still be 80 units off the
// plane. Measuring in 3D would read that sorting offset as being off the road.
// ---------------------------------------------------------------------------

namespace
{
	FVector ClosestOnSegmentXZ(const FVector& P, const FVector& A, const FVector& B)
	{
		const FVector2D P2(P.X, P.Z);
		const FVector2D A2(A.X, A.Z);
		const FVector2D B2(B.X, B.Z);
		const FVector2D AB = B2 - A2;
		const float LenSq = AB.SizeSquared();
		if (LenSq <= KINDA_SMALL_NUMBER)
		{
			return FVector(A.X, P.Y, A.Z);
		}
		const float T = FMath::Clamp(FVector2D::DotProduct(P2 - A2, AB) / LenSq, 0.0f, 1.0f);
		const FVector2D On = A2 + AB * T;
		return FVector(On.X, P.Y, On.Y);
	}

	float DistanceXZ(const FVector& A, const FVector& B)
	{
		return FVector2D(A.X - B.X, A.Z - B.Z).Size();
	}

	float DistanceToSegmentXZ(const FVector& P, const FVector& A, const FVector& B)
	{
		return DistanceXZ(P, ClosestOnSegmentXZ(P, A, B));
	}
}

bool APTKBattlefield::IsWalkable(const FVector& World) const
{
	// Platforms first: they are the widest walkable areas and the places a
	// guard is most often standing, so testing them first usually answers the
	// question without touching the road loop at all.
	for (const FPTKLaneNode& Node : LaneNodes)
	{
		const FString Id = Node.Id.ToString();
		const bool bCore = Id == TEXT("KING");
		const bool bPlatform = bCore || Id.StartsWith(TEXT("B_"));
		if (!bPlatform)
		{
			continue;
		}
		const float Radius = bCore ? CoreRadius : PlatformRadius;
		const FVector Where = NormalisedToWorld(Node.Normalised);
		if (DistanceXZ(World, Where) <= Radius)
		{
			return true;
		}
	}

	// Then the roads. Every edge is walked once; Links are undirected, so an
	// edge listed from either end covers both.
	for (const FPTKLaneNode& Node : LaneNodes)
	{
		const FVector A = NormalisedToWorld(Node.Normalised);
		for (const FName& LinkId : Node.Links)
		{
			const FVector B = GetNodeLocation(LinkId);
			if (DistanceToSegmentXZ(World, A, B) <= RoadHalfWidth)
			{
				return true;
			}
		}
	}
	return false;
}

FVector APTKBattlefield::FindNearestWalkable(const FVector& World) const
{
	if (IsWalkable(World))
	{
		return World;
	}

	// Closest point on any road centre-line. Platforms sit on the graph too, so
	// this also recovers something stranded beside one.
	FVector Best = MapCentre;
	float BestSq = TNumericLimits<float>::Max();

	for (const FPTKLaneNode& Node : LaneNodes)
	{
		const FVector A = NormalisedToWorld(Node.Normalised);
		for (const FName& LinkId : Node.Links)
		{
			const FVector B = GetNodeLocation(LinkId);
			const FVector OnSeg = ClosestOnSegmentXZ(World, A, B);
			const float Dist = DistanceXZ(World, OnSeg);
			if (Dist < BestSq)
			{
				BestSq = Dist;
				Best = OnSeg;
			}
		}
	}
	Best.Y = World.Y;
	return Best;
}

const FPTKLaneRoute* APTKBattlefield::FindRoute(FName RouteId) const
{
	return Routes.FindByPredicate([RouteId](const FPTKLaneRoute& R) { return R.Id == RouteId; });
}

TArray<FName> APTKBattlefield::GetRouteIdsForPortal(FName PortalId) const
{
	TArray<FName> Out;
	for (const FPTKLaneRoute& R : Routes)
	{
		if (R.PortalId == PortalId)
		{
			Out.Add(R.Id);
		}
	}
	return Out;
}

int32 APTKBattlefield::GetRouteLength(FName RouteId) const
{
	const FPTKLaneRoute* Route = FindRoute(RouteId);
	return Route ? Route->Nodes.Num() : 0;
}

FVector APTKBattlefield::GetRouteStepLocation(FName RouteId, int32 Step) const
{
	const FPTKLaneRoute* Route = FindRoute(RouteId);
	if (!Route || !Route->Nodes.IsValidIndex(Step))
	{
		return MapCentre;
	}
	return GetNodeLocation(Route->Nodes[Step]);
}

namespace
{
	/** Distance from P to segment AB, on the play plane. */
	float DistanceToSegment(const FVector& P, const FVector& A, const FVector& B)
	{
		const FVector AB = B - A;
		const float LenSq = AB.SizeSquared();
		if (LenSq <= KINDA_SMALL_NUMBER)
		{
			return FVector::Dist(P, A);
		}
		const float T = FMath::Clamp(FVector::DotProduct(P - A, AB) / LenSq, 0.0f, 1.0f);
		return FVector::Dist(P, A + AB * T);
	}
}

float APTKBattlefield::DistanceToRoute(FName RouteId, const FVector& World) const
{
	const FPTKLaneRoute* Route = FindRoute(RouteId);
	if (!Route || Route->Nodes.Num() == 0)
	{
		return TNumericLimits<float>::Max();
	}
	if (Route->Nodes.Num() == 1)
	{
		return FVector::Dist(World, GetNodeLocation(Route->Nodes[0]));
	}

	float Best = TNumericLimits<float>::Max();
	for (int32 i = 0; i + 1 < Route->Nodes.Num(); ++i)
	{
		Best = FMath::Min(Best, DistanceToSegment(World,
			GetNodeLocation(Route->Nodes[i]), GetNodeLocation(Route->Nodes[i + 1])));
	}
	return Best;
}

float APTKBattlefield::GetRouteProgress(FName RouteId, const FVector& World) const
{
	const FPTKLaneRoute* Route = FindRoute(RouteId);
	if (!Route || Route->Nodes.Num() < 2)
	{
		return 0.0f;
	}

	// Walk the polyline, tracking total length and the length up to the closest
	// point. The ratio is how far along the lane the point has travelled.
	float Total = 0.0f;
	float AtClosest = 0.0f;
	float BestDist = TNumericLimits<float>::Max();

	for (int32 i = 0; i + 1 < Route->Nodes.Num(); ++i)
	{
		const FVector A = GetNodeLocation(Route->Nodes[i]);
		const FVector B = GetNodeLocation(Route->Nodes[i + 1]);
		const float SegLen = FVector::Dist(A, B);
		const float Dist = DistanceToSegment(World, A, B);
		if (Dist < BestDist)
		{
			BestDist = Dist;
			const FVector AB = B - A;
			const float LenSq = FMath::Max(AB.SizeSquared(), KINDA_SMALL_NUMBER);
			const float T = FMath::Clamp(FVector::DotProduct(World - A, AB) / LenSq, 0.0f, 1.0f);
			AtClosest = Total + SegLen * T;
		}
		Total += SegLen;
	}
	return Total > KINDA_SMALL_NUMBER ? FMath::Clamp(AtClosest / Total, 0.0f, 1.0f) : 0.0f;
}

void APTKBattlefield::RebuildNodeIndex()
{
	NodeIndex.Reset();
	for (int32 i = 0; i < LaneNodes.Num(); ++i)
	{
		NodeIndex.Add(LaneNodes[i].Id, i);
	}

	// Edges are authored on one side only; make them symmetric here so the
	// search never has to care which end declared the road.
	Adjacency.Reset();
	Adjacency.SetNum(LaneNodes.Num());
	for (int32 i = 0; i < LaneNodes.Num(); ++i)
	{
		for (const FName& Link : LaneNodes[i].Links)
		{
			const int32* Found = NodeIndex.Find(Link);
			if (!Found)
			{
				UE_LOG(LogPTK, Warning, TEXT("BATTLEFIELD | lane node %s links to unknown node %s"),
					*LaneNodes[i].Id.ToString(), *Link.ToString());
				continue;
			}
			Adjacency[i].AddUnique(*Found);
			Adjacency[*Found].AddUnique(i);
		}
	}
}

FVector APTKBattlefield::GetNodeLocation(FName NodeId) const
{
	if (const int32* Found = NodeIndex.Find(NodeId))
	{
		return NormalisedToWorld(LaneNodes[*Found].Normalised);
	}
	return MapCentre;
}

FName APTKBattlefield::FindNearestNode(const FVector& World) const
{
	FName Best = NAME_None;
	float BestSq = TNumericLimits<float>::Max();
	for (const FPTKLaneNode& Node : LaneNodes)
	{
		const FVector At = NormalisedToWorld(Node.Normalised);
		const float Sq = FVector::DistSquared2D(FVector(At.X, At.Z, 0.0f), FVector(World.X, World.Z, 0.0f));
		if (Sq < BestSq)
		{
			BestSq = Sq;
			Best = Node.Id;
		}
	}
	return Best;
}

void APTKBattlefield::ComputeDistancesFrom(int32 StartIndex, TArray<float>& OutCost, TArray<int32>& OutPrev) const
{
	const int32 Count = LaneNodes.Num();
	OutCost.Init(UnreachableCost, Count);
	OutPrev.Init(INDEX_NONE, Count);
	if (!LaneNodes.IsValidIndex(StartIndex))
	{
		return;
	}
	OutCost[StartIndex] = 0.0f;

	// The graph is a couple of dozen nodes, so a linear scan for the cheapest
	// open node costs less than maintaining a heap would.
	TArray<bool> Visited;
	Visited.Init(false, Count);
	for (int32 Step = 0; Step < Count; ++Step)
	{
		int32 Current = INDEX_NONE;
		float Best = UnreachableCost;
		for (int32 i = 0; i < Count; ++i)
		{
			if (!Visited[i] && OutCost[i] < Best)
			{
				Best = OutCost[i];
				Current = i;
			}
		}
		if (Current == INDEX_NONE)
		{
			break;
		}
		Visited[Current] = true;

		const FVector From = NormalisedToWorld(LaneNodes[Current].Normalised);
		for (int32 Next : Adjacency[Current])
		{
			if (Visited[Next])
			{
				continue;
			}
			const FVector To = NormalisedToWorld(LaneNodes[Next].Normalised);
			const float Edge = FVector::Dist(From, To);
			if (OutCost[Current] + Edge < OutCost[Next])
			{
				OutCost[Next] = OutCost[Current] + Edge;
				OutPrev[Next] = Current;
			}
		}
	}
}

float APTKBattlefield::GetPathDistance(const FVector& From, const FVector& To) const
{
	const int32* StartIdx = NodeIndex.Find(FindNearestNode(From));
	const int32* EndIdx = NodeIndex.Find(FindNearestNode(To));
	if (!StartIdx || !EndIdx)
	{
		return FVector::Dist(From, To);
	}

	// The straight runs from each point onto the road are added back, so two
	// things sharing a node do not come out zero apart.
	const float ToRoad = FVector::Dist(From, NormalisedToWorld(LaneNodes[*StartIdx].Normalised));
	const float FromRoad = FVector::Dist(To, NormalisedToWorld(LaneNodes[*EndIdx].Normalised));

	if (*StartIdx == *EndIdx)
	{
		return FVector::Dist(From, To);
	}

	TArray<float> Cost;
	TArray<int32> Prev;
	ComputeDistancesFrom(*StartIdx, Cost, Prev);
	return Cost[*EndIdx] >= UnreachableCost ? UnreachableCost : Cost[*EndIdx] + ToRoad + FromRoad;
}

bool APTKBattlefield::GetNextLaneStep(const FVector& From, const FVector& To, FVector& OutStep) const
{
	if (LaneNodes.Num() == 0)
	{
		return false;
	}

	const int32* StartIdx = NodeIndex.Find(FindNearestNode(From));
	const int32* EndIdx = NodeIndex.Find(FindNearestNode(To));
	if (!StartIdx || !EndIdx)
	{
		return false;
	}

	// Already on the target's own node: the road has done its job and the last
	// stretch is a straight walk. Without this an enemy would orbit the node
	// rather than close on what it came for.
	if (*StartIdx == *EndIdx)
	{
		OutStep = To;
		return true;
	}

	TArray<float> Cost;
	TArray<int32> Prev;
	ComputeDistancesFrom(*StartIdx, Cost, Prev);
	if (Cost[*EndIdx] >= UnreachableCost)
	{
		return false;
	}

	// Walk the chain back from the destination until the step before the start;
	// that node is the next one to head for.
	int32 Trace = *EndIdx;
	while (Prev[Trace] != INDEX_NONE && Prev[Trace] != *StartIdx)
	{
		Trace = Prev[Trace];
	}
	OutStep = NormalisedToWorld(LaneNodes[Trace].Normalised);
	return true;
}

// ---------------------------------------------------------------------------
// Objective registry
// ---------------------------------------------------------------------------

void APTKBattlefield::RegisterGuard(APTKGuardCharacter* Guard)
{
	if (Guard)
	{
		Guards.AddUnique(Guard);
	}
}

void APTKBattlefield::UnregisterGuard(APTKGuardCharacter* Guard)
{
	Guards.Remove(Guard);
}

void APTKBattlefield::RegisterBase(APTKGuardBase* Base)
{
	if (Base)
	{
		Bases.AddUnique(Base);
	}
}

void APTKBattlefield::UnregisterBase(APTKGuardBase* Base)
{
	Bases.Remove(Base);
}

void APTKBattlefield::RegisterPortal(APTKSpawnPortal* Portal)
{
	if (Portal)
	{
		Portals.AddUnique(Portal);
	}
}

APTKKingCharacter* APTKBattlefield::GetKing() const
{
	if (CachedKing && IsValid(CachedKing))
	{
		return CachedKing;
	}
	for (TActorIterator<APTKKingCharacter> It(GetWorld()); It; ++It)
	{
		CachedKing = *It;
		return CachedKing;
	}
	return nullptr;
}

APTKGuardBase* APTKBattlefield::FindBaseForGuard(FName GuardId) const
{
	for (const TObjectPtr<APTKGuardBase>& Base : Bases)
	{
		if (Base && Base->GetGuardId() == GuardId)
		{
			return Base;
		}
	}
	return nullptr;
}

UPTKAnalyticsSubsystem* APTKBattlefield::GetAnalytics() const
{
	return UPTKAnalyticsSubsystem::Get(GetWorld());
}

UPTKAdaptiveDirector* APTKBattlefield::GetDirector() const
{
	return UPTKAdaptiveDirector::Get(GetWorld());
}
