// Protect the King - 2D. Watches a run and writes down what happened.

#pragma once

#include "CoreMinimal.h"
#include "Analytics/PTKAnalyticsTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "PTKAnalyticsSubsystem.generated.h"

class APTKEnemyCharacter;
class APTKGuardBase;
class APTKGuardCharacter;
class UPTKHealthComponent;

/**
 * UPTKAnalyticsSubsystem
 * ======================
 * Records what the player and the horde did, wave by wave, and scores it.
 *
 * This phase ONLY observes. Nothing here changes spawning, targeting or
 * difficulty - the point is to have a truthful record first, so that when a
 * later phase does start adapting, it is adapting to something real rather
 * than to a metric that turned out to measure the wrong thing.
 *
 *
 * WHY A SUBSYSTEM AND NOT AN ACTOR
 * --------------------------------
 * Every other coordinator in this project is an actor placed in the level,
 * which means adding one costs a level rebuild and a .umap change. A world
 * subsystem exists automatically in every world, needs no placement, and is
 * destroyed with the world - so Restart and New Game reset the run's history
 * for free, with no reset code to forget to write.
 *
 *
 * EVENT-DRIVEN, NOT POLLED
 * ------------------------
 * Damage, kills, spawns, deaths, possession changes, King casts and base
 * destruction all ARRIVE here - nothing goes looking for them. The class never
 * calls GetAllActorsOfClass: the set of live enemies is maintained by the spawn
 * and death events themselves.
 *
 * Two things genuinely cannot be events, because they are questions about
 * position rather than about something that happened:
 *
 *     which lane the player is standing in
 *     how far along its lane the deepest enemy has got
 *
 * Those are sampled on a timer (SampleInterval, default twice a second) rather
 * than per frame. At that rate the cost is a few hundred distance tests a
 * second against a cached list, and the answer is no less true for being a
 * fifth of a second old.
 */
UCLASS()
class PROTECTTHEKING2D_API UPTKAnalyticsSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UPTKAnalyticsSubsystem* Get(const UWorld* World);

	// UTickableWorldSubsystem
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual bool DoesSupportWorldType(const EWorldType::Type Type) const override;

	// ------------------------------------------------------------------
	// Events. Everything the subsystem knows arrives through one of these.
	// ------------------------------------------------------------------

	/** A wave started. Opens a fresh set of counters. */
	void NotifyWaveBegan(int32 WaveNumber);

	/** A wave ended. Scores and freezes the counters into a snapshot. */
	void NotifyWaveEnded(int32 WaveNumber);

	/** An enemy was spawned onto a lane. */
	void NotifyEnemySpawned(APTKEnemyCharacter* Enemy, FName LaneId);

	/** The player took over a guard. Pass nullptr when they lose one. */
	void NotifyPossession(APTKGuardCharacter* Guard);

	/** The King empowered a guard. */
	void NotifyKingPower(APTKGuardCharacter* Guard);

	/** A base fell. */
	void NotifyBaseDestroyed(APTKGuardBase* Base);

	// ------------------------------------------------------------------
	// Reading the record
	// ------------------------------------------------------------------

	/** Every finished wave, oldest first. */
	UFUNCTION(BlueprintPure, Category = "PTK|Analytics")
	const TArray<FPTKWaveSnapshot>& GetSnapshots() const { return Snapshots; }

	/** The most recently frozen wave. Empty snapshot if none yet. */
	UFUNCTION(BlueprintPure, Category = "PTK|Analytics")
	FPTKWaveSnapshot GetLastSnapshot() const;

	/** The wave in progress, scored as it stands. For the HUD and for tests. */
	UFUNCTION(BlueprintPure, Category = "PTK|Analytics")
	FPTKWaveSnapshot GetLiveSnapshot() const;

	UFUNCTION(BlueprintPure, Category = "PTK|Analytics")
	bool IsTrackingWave() const { return bTracking; }

	/** Writes the whole history to the log. Verification aid. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Analytics")
	void LogHistory() const;

	// ------------------------------------------------------------------
	// Tuning. All weights sum to 1 within their own score.
	// ------------------------------------------------------------------

	/** Switches per minute at or below which the tempo reads Low. */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Switching")
	float LowSwitchesPerMinute = 4.0f;

	/** Switches per minute at or above which the tempo reads High. */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Switching")
	float HighSwitchesPerMinute = 12.0f;

	/** Player-control share above which one guard counts as the whole wave. */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Switching")
	float SingleGuardFocusFraction = 0.70f;

	/** Lane progress past which a lane counts as breached. */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane")
	float BreachProgress = 0.85f;

	/**
	 * Guard damage on one lane that counts as "as bad as it gets".
	 *
	 * Vulnerability needs every factor on a 0..1 scale or the weights mean
	 * nothing, and damage has no natural ceiling the way a base's health bar
	 * does. This is that ceiling, chosen rather than derived.
	 */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane")
	float GuardDamageReference = 2000.0f;

	// Lane vulnerability weights. Each factor is clamped to 0..1 before it is
	// weighted, so no single event can push the result past its own share -
	// a destroyed base is serious but it is not, by itself, a 1.0.
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane") float WeightBaseDamage = 0.25f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane") float WeightGuardDamage = 0.15f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane") float WeightEnemyProgress = 0.20f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane") float WeightLowPlayerPresence = 0.15f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane") float WeightBreach = 0.10f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Lane") float WeightBaseDestroyed = 0.15f;

	// Guard dominance weights. Player usage is deliberately the SMALLEST of
	// them: a guard the player drove all wave but achieved nothing with is not
	// the dominant guard, and defining dominance by usage would say it was.
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Guard") float WeightKillShare = 0.30f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Guard") float WeightDamageShare = 0.30f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Guard") float WeightSurvival = 0.15f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Guard") float WeightPlayerUsage = 0.10f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Guard") float WeightLaneSuccess = 0.15f;

	// Enemy effectiveness weights.
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Enemy") float WeightDamageToGuards = 0.25f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Enemy") float WeightDamageToBases = 0.25f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Enemy") float WeightDamageToKing = 0.20f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Enemy") float WeightEnemySurvival = 0.10f;
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics|Enemy") float WeightEnemyProgressReached = 0.20f;

	/** Seconds between position samples. Presence and progress only. */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics")
	float SampleInterval = 0.5f;

	/** How near a lane a guard must be to count as present on it. */
	UPROPERTY(EditAnywhere, Category = "PTK|Analytics")
	float LanePresenceRadius = 600.0f;

protected:
	// Damage and death arrive here from every tracked health component.
	UFUNCTION() void HandleGuardHealth(UPTKHealthComponent* Component, float NewHealth, float Delta, AActor* Instigator);
	UFUNCTION() void HandleGuardDeath(UPTKHealthComponent* Component, AActor* Killer);
	UFUNCTION() void HandleEnemyHealth(UPTKHealthComponent* Component, float NewHealth, float Delta, AActor* Instigator);
	UFUNCTION() void HandleEnemyDeath(UPTKHealthComponent* Component, AActor* Killer);
	UFUNCTION() void HandleBaseHealth(UPTKHealthComponent* Component, float NewHealth, float Delta, AActor* Instigator);
	UFUNCTION() void HandleKingHealth(UPTKHealthComponent* Component, float NewHealth, float Delta, AActor* Instigator);

private:
	/** Binds to the guards, bases and King once the battlefield exists. */
	void EnsureBound();

	/** The twice-a-second position pass. */
	void SamplePresenceAndProgress(float Elapsed);

	/** Working rows, keyed for cheap lookup while a wave is live. */
	FPTKGuardWaveStats& GuardRow(FName GuardId);
	FPTKLaneWaveStats& LaneRow(FName LaneId);
	FPTKEnemyTypeWaveStats& EnemyRow(FName EnemyId);

	/** Which lane an enemy actor was spawned onto. */
	FName LaneOf(const AActor* Enemy) const;

	/** Scores a snapshot in place. Called once, at freeze. */
	void ScoreSnapshot(FPTKWaveSnapshot& Snapshot) const;

	UPROPERTY() TArray<FPTKWaveSnapshot> Snapshots;

	/** Counters for the wave in progress. */
	FPTKWaveSnapshot Live;
	bool bTracking = false;
	bool bBound = false;
	float WaveStartTime = 0.0f;
	float SampleTimer = 0.0f;

	/** The guard the player is driving, and since when. */
	UPROPERTY() TObjectPtr<APTKGuardCharacter> PossessedGuard;
	float PossessionStartTime = 0.0f;
	float LastSwitchTime = 0.0f;
	TArray<float> SwitchIntervals;

	/**
	 * Live enemies, maintained by the spawn and death events.
	 *
	 * This is what lets the sampling pass avoid GetAllActorsOfClass: the list
	 * is already correct because nothing can join or leave it without the
	 * subsystem being told.
	 */
	UPROPERTY() TArray<TObjectPtr<APTKEnemyCharacter>> LiveEnemies;

	/** Enemy actor -> the lane it was dealt. Survives its death. */
	TMap<TWeakObjectPtr<const AActor>, FName> EnemyLane;

	/** Health component -> the guard base that owns it. */
	TMap<TWeakObjectPtr<UPTKHealthComponent>, FName> BaseByHealth;

	/** Guard id -> the lane whose base that guard defends. */
	TMap<FName, FName> LaneOfGuard;
};
