// Protect the King - 2D. Development enemy spawner.

#include "Core/PTKEnemySpawner.h"
#include "Core/PTKGameModeBase.h"

#include "Characters/PTKEnemyCharacter.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKEnemySpawner)

APTKEnemySpawner::APTKEnemySpawner()
{
	PrimaryActorTick.bCanEverTick = false;
}

void APTKEnemySpawner::BeginPlay()
{
	Super::BeginPlay();

	if (APTKGameModeBase::IsGameplayActive(GetWorld())) StartSpawning();
}

void APTKEnemySpawner::StartSpawning()
{
	if (bSpawnOnBeginPlay)
	{
		SpawnWave();
	}
}

int32 APTKEnemySpawner::SpawnWave()
{
	UWorld* const World = GetWorld();
	if (!APTKGameModeBase::IsGameplayActive(World))
	{
		return 0;
	}

	TArray<TSubclassOf<APTKEnemyCharacter>> Roster;
	if (EnemyClass)
	{
		for (int32 i = 0; i < FMath::Clamp(SpawnCount, 0, 200); ++i) Roster.Add(EnemyClass);
	}
	for (const FPTKEnemySpawnEntry& Entry : AdditionalEnemies)
	{
		if (!Entry.EnemyClass) continue;
		for (int32 i = 0; i < FMath::Clamp(Entry.Count, 0, 200); ++i) Roster.Add(Entry.EnemyClass);
	}
	ClearWave();
	if (Roster.IsEmpty())
	{
		UE_LOG(LogPTK, Warning,
			TEXT("%s has no configured enemies to spawn."), *GetName());
		return 0;
	}

	// Movement is locked to the XZ play plane, so the ring is laid out in
	// screen-right / screen-up and never given a Y component.
	const FVector Origin = GetActorLocation();
	FRandomStream Stream(RandomSeed);

	int32 Placed = 0;
	int32 Ring = 0;
	while (Placed < Roster.Num())
	{
		const float Radius = RingRadius + Ring * MinSeparation;

		// How many fit on this ring at MinSeparation spacing. The chord between
		// neighbours must be at least MinSeparation, so the slot count follows
		// from the circumference rather than being guessed.
		const int32 Capacity = FMath::Max(1,
			FMath::FloorToInt((2.0f * PI * Radius) / FMath::Max(1.0f, MinSeparation)));
		const int32 OnThisRing = FMath::Min(Capacity, Roster.Num() - Placed);

		// Offset alternate rings by half a slot so they interleave instead of
		// lining up into spokes.
		const float Phase = (Ring % 2) ? (PI / FMath::Max(1, OnThisRing)) : 0.0f;

		for (int32 i = 0; i < OnThisRing; ++i)
		{
			const float Angle = Phase + (2.0f * PI * i) / OnThisRing;
			const float JitterX = Stream.FRandRange(-PositionJitter, PositionJitter);
			const float JitterZ = Stream.FRandRange(-PositionJitter, PositionJitter);

			const FVector Location(
				Origin.X + FMath::Cos(Angle) * Radius + JitterX,
				Origin.Y,
				Origin.Z + FMath::Sin(Angle) * Radius + JitterZ);

			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride =
				ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
			Params.ObjectFlags |= RF_Transient;

			APTKEnemyCharacter* const Enemy = World->SpawnActor<APTKEnemyCharacter>(
				Roster[Placed], Location, FRotator::ZeroRotator, Params);

			if (Enemy)
			{
				// Labels exist only in editor builds; naming the spawned actors
				// is purely so they are readable in the outliner.
#if WITH_EDITOR
				Enemy->SetActorLabel(FString::Printf(TEXT("%s_Spawned_%02d"), *Enemy->GetEnemyId().ToString(), Placed + 1));
#endif
				Spawned.Add(Enemy);
				if (bDrawSpawnPoints)
				{
					DrawDebugSphere(World, Location, 20.0f, 12, FColor::Magenta, false, 8.0f);
				}
			}
			else
			{
				UE_LOG(LogPTK, Warning, TEXT("%s failed to spawn enemy %d"), *GetName(), Placed + 1);
			}
			++Placed;
		}

		++Ring;

		// Guard against an impossible configuration (radius 0 and separation
		// larger than any ring) turning into an endless loop.
		if (Ring > 64)
		{
			UE_LOG(LogPTK, Warning,
				TEXT("%s gave up after 64 rings - check RingRadius / MinSeparation."), *GetName());
			break;
		}
	}

	UE_LOG(LogPTK, Log, TEXT("%s spawned %d/%d enemies across %d ring(s)"),
		*GetName(), Spawned.Num(), Roster.Num(), Ring);
	return Spawned.Num();
}

void APTKEnemySpawner::ClearWave()
{
	for (APTKEnemyCharacter* const Enemy : Spawned)
	{
		if (IsValid(Enemy))
		{
			Enemy->Destroy();
		}
	}
	Spawned.Reset();
}
