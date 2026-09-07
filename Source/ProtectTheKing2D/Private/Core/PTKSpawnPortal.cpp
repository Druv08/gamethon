#include "Core/PTKSpawnPortal.h"

#include "Core/PTKBattlefield.h"
#include "ProtectTheKing2D.h"

APTKSpawnPortal::APTKSpawnPortal()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	// A portal IS a location, so it needs a root to hold one. Without this the
	// actor has no transform at all and every portal silently reports the world
	// origin - which places four spawn corners on top of the King.
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

void APTKSpawnPortal::BeginPlay()
{
	Super::BeginPlay();
	if (APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		Field->RegisterPortal(this);
	}
	UE_LOG(LogPTK, Log, TEXT("PORTAL | %s at %s"), *PortalId.ToString(), *GetActorLocation().ToString());
}

void APTKSpawnPortal::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (WarningRemaining > 0.0f)
	{
		WarningRemaining = FMath::Max(WarningRemaining - DeltaSeconds, 0.0f);
	}
}

FVector APTKSpawnPortal::PickSpawnPoint(FRandomStream& Stream) const
{
	// Uniform by area rather than by radius: sampling the radius linearly
	// clusters points near the centre, which is the stacking this is meant to
	// avoid in the first place.
	const float MinSq = FMath::Square(MinSpawnRadius);
	const float MaxSq = FMath::Square(SpawnRadius);
	const float Radius = FMath::Sqrt(Stream.FRandRange(MinSq, FMath::Max(MaxSq, MinSq + 1.0f)));
	const float Angle = Stream.FRandRange(0.0f, 2.0f * PI);

	const FVector Centre = GetActorLocation();
	FVector Point(
		Centre.X + Radius * FMath::Cos(Angle),
		Centre.Y,
		Centre.Z + Radius * FMath::Sin(Angle));

	if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		Point = Field->ClampToMap(Point, 80.0f);
	}
	return Point;
}

void APTKSpawnPortal::BeginWarning(float Seconds)
{
	WarningRemaining = FMath::Max(Seconds, 0.0f);
	UE_LOG(LogPTK, Log, TEXT("PORTAL WARNING | %s | %.1fs"), *PortalId.ToString(), WarningRemaining);
}

void APTKSpawnPortal::ClearWarning()
{
	WarningRemaining = 0.0f;
}
