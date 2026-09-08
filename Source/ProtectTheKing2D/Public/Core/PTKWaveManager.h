// Protect the King - 2D. The wave system: what arrives, from where, and when.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PTKWaveManager.generated.h"

class APTKEnemyCharacter;
class APTKSpawnPortal;

/** One enemy type's share of a wave. Weights are relative, not percentages. */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKWaveEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave")
	TSubclassOf<APTKEnemyCharacter> EnemyClass;

	/** Relative share. A 3 alongside a 1 arrives about three times as often. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "0"))
	int32 Weight = 1;
};

/**
 * One wave.
 *
 * Composition is weighted rather than an explicit list of counts, which is what
 * makes repeated games differ: "twelve enemies drawn from mostly-swarm" gives a
 * different twelve each run, where "nine swarm and three infiltrators" gives the
 * same nine every time.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKWaveDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave")
	FText WaveName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "1", ClampMax = "300"))
	int32 EnemyCount = 10;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave")
	TArray<FPTKWaveEntry> Composition;

	/**
	 * How many of the four corners this wave arrives from.
	 *
	 * Which corners is chosen at random each run, so a wave that uses two of
	 * them is not always the same two - the "different attack angles" the
	 * balance section leans on.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "1", ClampMax = "4"))
	int32 PortalCount = 1;

	/** Seconds between individual arrivals, so a wave walks in rather than blinking in. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "0.0"))
	float SpawnInterval = 0.35f;
};

/** Where the run currently is. Drives both the HUD and what Tick does. */
UENUM(BlueprintType)
enum class EPTKWavePhase : uint8
{
	/** Before Enter is pressed. Nothing has been scheduled. */
	Idle		UMETA(DisplayName = "Idle"),
	/** Portals are lit and counting down; nothing has spawned yet. */
	Warning		UMETA(DisplayName = "Incoming"),
	/** Trickling the wave's enemies in. */
	Spawning	UMETA(DisplayName = "Spawning"),
	/** Everything is out; waiting for the field to be cleared. */
	Fighting	UMETA(DisplayName = "Fighting"),
	/** Wave cleared, next one counting down. */
	Intermission UMETA(DisplayName = "Intermission"),
	/** Every wave cleared. */
	Complete	UMETA(DisplayName = "Complete"),
	/** The King fell; the run is over and nothing more will spawn. */
	Stopped		UMETA(DisplayName = "Stopped")
};

/**
 * APTKWaveManager
 * ===============
 * Runs the five waves: picks what arrives, warns the player where it is coming
 * from, spawns it across the chosen corners, and decides when the run is won.
 *
 * This replaces APTKEnemySpawner's development behaviour of dropping N enemies
 * in a ring at BeginPlay. That spawner still exists and still works - it is a
 * useful stress-test tool - but it is no longer what a real game uses.
 *
 *
 * WHY THE WARNING IS A PHASE AND NOT A NOTIFICATION
 * -------------------------------------------------
 * The spec asks for 2-3 seconds of warning at the spawn area BEFORE the horde
 * appears. Making that a phase of this state machine, rather than a message
 * fired at the HUD, means the warning cannot get out of step with the spawn: the
 * enemies are spawned BY the transition out of Warning, so a visible warning
 * always precedes them and a spawn can never happen without one.
 *
 *
 * SCALING IS APPLIED TO INSTANCES, NEVER TO THE BLUEPRINT
 * -------------------------------------------------------
 * Later waves are harder because each spawned enemy has its max health and its
 * damage multiplier set as it enters the world. The Blueprint's own defaults are
 * never written to. That distinction matters more than it looks: a CDO edit
 * would persist into the next Play session and into the asset on disk, so a run
 * to wave 5 would permanently leave every Swarm Node in the project at 1.5x
 * health with nothing recording why.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKWaveManager : public AActor
{
	GENERATED_BODY()

public:
	APTKWaveManager();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** The one wave manager in this world, or nullptr. */
	static APTKWaveManager* Get(const UWorld* World);

	/** Called by the game mode when Enter starts the game. Idempotent. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Wave")
	void StartRun();

	/** Halts everything permanently - used when the King falls. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Wave")
	void StopRun();

	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	EPTKWavePhase GetPhase() const { return Phase; }

	/** 1-based, for the HUD. Zero before the first wave. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	int32 GetCurrentWave() const { return CurrentWave; }

	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	int32 GetTotalWaves() const { return Waves.Num(); }

	/** Living enemies from the current wave that are still on the field. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	int32 GetEnemiesRemaining() const;

	/** Seconds until the next wave, during Intermission/Warning. Zero otherwise. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	float GetCountdown() const { return PhaseTimer; }

	/** True once every wave has been cleared. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	bool IsRunComplete() const { return Phase == EPTKWavePhase::Complete; }

	/** Portals the incoming wave will use. Empty outside Warning/Spawning. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	TArray<APTKSpawnPortal*> GetActivePortals() const;

	/** Lanes this wave is being dealt onto. Drives the minimap's lane warnings. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	TArray<FName> GetActiveRoutes() const { return ActiveRoutes; }

	/**
	 * The seed this run is actually using.
	 *
	 * Every random choice a run makes - which corners open, which lanes the
	 * horde is dealt onto, what each wave is made of - comes from this one
	 * number, so replaying it reproduces the run and changing it produces a
	 * different one. That is the whole difference between Restart and New Game.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	int32 GetActiveSeed() const { return ActiveSeed; }

	/**
	 * Test aid: spawns extra enemies onto the lanes already in play.
	 *
	 * For load testing only, and deliberately separate from the wave
	 * definitions - pushing the field to a hundred bodies has to be possible
	 * WITHOUT editing what a normal wave contains, or the thing measured is no
	 * longer the thing shipped. Never called by the game itself.
	 *
	 * Returns how many actually spawned.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Wave|Debug")
	int32 DebugSpawnExtra(int32 Count);

	/** Everything this manager has spawned and not yet buried. C++ only. */
	const TArray<TObjectPtr<APTKEnemyCharacter>>& GetLiveEnemies() const { return Live; }

	/** Health multiplier currently applied to new arrivals. */
	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	float GetHealthScaleForWave(int32 Wave) const;

	UFUNCTION(BlueprintPure, Category = "PTK|Wave")
	float GetDamageScaleForWave(int32 Wave) const;

	/** Skips straight to the next wave. Manual testing aid. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Wave|Debug")
	void DebugSkipToWave(int32 Wave);

protected:
	/** Chooses portals, lights their warnings and enters Warning. */
	void BeginWave(int32 Wave);

	/** Rolls the whole wave's roster up front so the mix is known before it lands. */
	void RollComposition(const FPTKWaveDefinition& Definition, TArray<TSubclassOf<APTKEnemyCharacter>>& OutRoster);

	/** Spawns one enemy at one of the active portals. */
	bool SpawnOne(TSubclassOf<APTKEnemyCharacter> EnemyClass);

	/** Drops references to anything dead, so the remaining count stays honest. */
	void PruneDead();

	/** Fills Waves with the five-wave prototype when none was authored. */
	void BuildDefaultWaves();

	// ------------------------------------------------------------------
	// Authored data
	// ------------------------------------------------------------------

	/**
	 * Enemy Blueprints by id, so the default wave table can be written without
	 * five more EditAnywhere class pointers to wire up per level.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave")
	TMap<FName, TSubclassOf<APTKEnemyCharacter>> EnemyTypes;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave")
	TArray<FPTKWaveDefinition> Waves;

	/** Seconds a portal glows before its horde arrives. Spec asks for 2-3. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "0.0"))
	float WarningDuration = 2.5f;

	/** Quiet time between a wave being cleared and the next warning. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "0.0"))
	float IntermissionDuration = 8.0f;

	/** Compounding health growth per wave beyond the first. Spec: 10-12%. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float HealthGrowthPerWave = 0.11f;

	/** Compounding damage growth per wave beyond the first. Spec: 5-8%. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DamageGrowthPerWave = 0.06f;

	/** 0 seeds from the clock, so spawn layouts differ per run. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Wave")
	int32 RandomSeed = 0;

	// ------------------------------------------------------------------
	// Runtime
	// ------------------------------------------------------------------

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Wave")
	EPTKWavePhase Phase = EPTKWavePhase::Idle;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Wave")
	int32 CurrentWave = 0;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Wave")
	float PhaseTimer = 0.0f;

	UPROPERTY()
	TArray<TObjectPtr<APTKEnemyCharacter>> Live;

	UPROPERTY()
	TArray<TObjectPtr<APTKSpawnPortal>> ActivePortals;

	/**
	 * Lanes this wave is using, one entry per route the chosen portals feed.
	 *
	 * Enemies are dealt onto these round-robin rather than each picking for
	 * itself. Independent choice is what produced the pathological case the
	 * spec describes: with every enemy free to pick, they all pick alike, and
	 * a whole wave lands on one or two defenders.
	 */
	UPROPERTY()
	TArray<FName> ActiveRoutes;

private:
	/** The wave's roster, popped one at a time during Spawning. */
	TArray<TSubclassOf<APTKEnemyCharacter>> PendingRoster;

	float SpawnTimer = 0.0f;

	/** Next slot in ActiveRoutes to deal from. */
	int32 RouteCursor = 0;

	FRandomStream Stream;

	/** Whatever Stream was actually initialised with. Read via GetActiveSeed. */
	UPROPERTY(VisibleInstanceOnly, Category = "PTK|Wave")
	int32 ActiveSeed = 0;
};
