// Protect the King - 2D. Development enemy spawner.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PTKEnemySpawner.generated.h"

class APTKEnemyCharacter;

/**
 * APTKEnemySpawner
 * ================
 * Drops N enemies into the arena on game start so combat can be stress-tested.
 *
 * This is a DEVELOPMENT TOOL, not the wave system. There are no rounds, no
 * timers, no budgets, no difficulty curve and no respawning - it exists so that
 * changing one number turns a 1v1 into a 20v1 and back again.
 *
 * Placement is a spaced ring rather than a random scatter, because random
 * points in a disc clump: with ten enemies and a 300 unit radius, uniform
 * sampling reliably drops two of them on top of each other, and two characters
 * spawned inside one another start the match resolving penetration instead of
 * walking. A ring guarantees a minimum arc between neighbours, and a fixed
 * random stream adds jitter without ever making the layout unreproducible.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKEnemySpawner : public AActor
{
	GENERATED_BODY()

public:
	APTKEnemySpawner();

	virtual void BeginPlay() override;
	void StartSpawning();

	/** Spawns SpawnCount enemies. Returns how many actually reached the world. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Spawner")
	int32 SpawnWave();

	/** Removes everything this spawner created. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Spawner")
	void ClearWave();

protected:
	/** What to spawn. Set to BP_SwarmNode. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner")
	TSubclassOf<APTKEnemyCharacter> EnemyClass;

	/**
	 * How many to spawn. The one number to change for a stress test:
	 * 1, 5, 10, 20 all work without touching anything else.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner", meta = (ClampMin = "0", ClampMax = "200"))
	int32 SpawnCount = 10;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner")
	// Retained for map serialization; automatic spawning now waits for StartGame.
	bool bSpawnOnBeginPlay = true;

	/** Radius of the innermost ring, in world units. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner", meta = (ClampMin = "0.0"))
	float RingRadius = 240.0f;

	/**
	 * Minimum spacing between neighbours. When a ring cannot hold SpawnCount at
	 * this spacing, another ring is started further out rather than packing them
	 * tighter - which is what stops a large count from spawning inside itself.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner", meta = (ClampMin = "1.0"))
	float MinSeparation = 90.0f;

	/** Random offset applied to each slot, so a ring does not look mechanical. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner", meta = (ClampMin = "0.0"))
	float PositionJitter = 28.0f;

	/** Fixed seed: the same layout every run, so a bug is reproducible. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Spawner")
	int32 RandomSeed = 20260905;

	/** Draws the computed spawn points for a few seconds at BeginPlay. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Debug")
	bool bDrawSpawnPoints = false;

	/** Everything spawned, so ClearWave can undo it. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Spawner")
	TArray<TObjectPtr<APTKEnemyCharacter>> Spawned;
};
