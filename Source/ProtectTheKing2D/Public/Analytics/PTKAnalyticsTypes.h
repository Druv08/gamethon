// Protect the King - 2D. What a wave looked like, once it is over.

#pragma once

#include "CoreMinimal.h"
#include "PTKAnalyticsTypes.generated.h"

/** How often the player changed guard, coarsely. */
UENUM(BlueprintType)
enum class EPTKSwitchTempo : uint8
{
	Low		UMETA(DisplayName = "Low"),
	Medium	UMETA(DisplayName = "Medium"),
	High	UMETA(DisplayName = "High")
};

/**
 * One guard's wave.
 *
 * PlayerControlledSeconds counts HUMAN possession only. A guard that walked
 * across the map on its own to help a neighbour was doing that by itself, and
 * counting it as player behaviour would make the AI look like a habit of the
 * player's - which is precisely the thing later phases will try to read.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKGuardWaveStats
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") FName GuardId;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float PlayerControlledSeconds = 0.0f;
	/** Share of the wave's total player-controlled time, 0..1. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float PlayerControlFraction = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 TimesSwitchedInto = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DamageDealt = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 Kills = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DamageTaken = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") bool bAlive = true;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") bool bReceivedKingPower = false;
	/** Health fraction at the moment the wave ended. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float HealthFraction = 1.0f;
	/** 0..1, computed when the wave is frozen. See ComputeDominance. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float Dominance = 0.0f;
};

/** How the player moved between guards. */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKSwitchStats
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 TotalSwitches = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float SwitchesPerMinute = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float AverageSecondsBetween = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") EPTKSwitchTempo Tempo = EPTKSwitchTempo::Low;
	/** One guard held most of the wave. See SingleGuardFocusFraction. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") bool bSingleGuardFocus = false;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") FName FocusGuardId;
};

/**
 * One lane's wave.
 *
 * PlayerPresence and AIAssistPresence are deliberately separate numbers. A lane
 * the player personally defended and a lane the AI covered for them look
 * identical if the two are summed, and they mean opposite things about what the
 * player is actually doing.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKLaneWaveStats
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") FName LaneId;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") FName BaseId;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 EnemiesSpawned = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 EnemyKills = 0;
	/** Furthest any enemy on this lane got toward the core, 0..1. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DeepestProgress = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float PlayerPresenceSeconds = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float AIAssistPresenceSeconds = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float GuardDamageTaken = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float BaseDamageTaken = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") bool bBaseDestroyed = false;
	/** An enemy on this lane got past BreachProgress toward the core. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") bool bBreached = false;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float KingDamageFromLane = 0.0f;
	/** 0..1, computed when the wave is frozen. See ComputeVulnerability. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float Vulnerability = 0.0f;
};

/** How one enemy type performed across a wave. */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKEnemyTypeWaveStats
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") FName EnemyId;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 Spawned = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 Died = 0;
	/** Share that were still alive when the wave was frozen, 0..1. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float SurvivalFraction = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DamageToGuards = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DamageToBases = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DamageToKing = 0.0f;
	/** Guards this type killed. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 GuardKills = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DeepestProgress = 0.0f;
	/** 0..1, computed when the wave is frozen. See ComputeEffectiveness. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float Effectiveness = 0.0f;
};

/**
 * A finished wave, frozen.
 *
 * Written once when the wave ends and never touched again, so later phases can
 * read a stable history rather than a set of counters still being mutated by
 * the fight going on around them.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKWaveSnapshot
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") int32 WaveNumber = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float DurationSeconds = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") float TotalPlayerControlledSeconds = 0.0f;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") TArray<FPTKGuardWaveStats> Guards;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") FPTKSwitchStats Switching;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") TArray<FPTKLaneWaveStats> Lanes;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Analytics") TArray<FPTKEnemyTypeWaveStats> EnemyTypes;
};
