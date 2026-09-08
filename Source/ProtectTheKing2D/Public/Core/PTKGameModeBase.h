// Protect the King - 2D. Base game mode.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "PTKGameModeBase.generated.h"

/**
 * How the run ended.
 *
 * Deliberately one value rather than a pair of booleans: "won and lost" is not
 * a state the game has, and a single enum makes that unrepresentable instead of
 * merely unlikely.
 */
UENUM(BlueprintType)
enum class EPTKMatchResult : uint8
{
	InProgress	UMETA(DisplayName = "In Progress"),
	Victory		UMETA(DisplayName = "Victory"),
	Defeat		UMETA(DisplayName = "Defeat")
};

/**
 * APTKGameModeBase
 * ================
 * Owns the one-way WaitingToStart -> Playing transition, and the equally
 * one-way transition out of Playing into Victory or Defeat.
 *
 * Both endings stop the same things - the wave manager, the spawners, combat
 * input - which is why they are resolved here rather than at the two places
 * that detect them. The King's death and the last wave being cleared are
 * events; deciding what they MEAN is one job in one place.
 *
 * A guard dying is not one of those events, by design. The line falling is a
 * problem for the player, not the end of the run: the King can still be
 * defended by whoever is left, and the enemy still has to walk in and finish
 * the job.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKGameModeBase : public AGameModeBase
{
	GENERATED_BODY()

public:
	APTKGameModeBase();

	UFUNCTION(BlueprintCallable, Category = "PTK|Start")
	void StartGame();

	UFUNCTION(BlueprintPure, Category = "PTK|Start")
	bool IsPlaying() const { return bPlaying; }

	/** True only while the fight is live: started, and not yet won or lost. */
	static bool IsGameplayActive(const UWorld* World);

	// ------------------------------------------------------------------
	// Ending a run and starting another
	// ------------------------------------------------------------------

	/**
	 * Replays the current run: same map, same wave seed.
	 *
	 * Both this and NewGame reload the level rather than unwinding the world by
	 * hand. Resetting in place would mean finding and undoing every piece of
	 * state a run accumulates - enemy actors, projectiles in flight, base
	 * damage, ruins, boosts, cooldowns, wave progress, minimap warnings, who is
	 * possessing whom - and any one of them missed leaves a subtly poisoned
	 * second run. A reload cannot miss any of it.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Flow")
	void RestartRun();

	/** A fresh run: same map, newly randomised corners, lanes and composition. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Flow")
	void NewGameRun();

	/**
	 * Takes the seed left for the next level load, clearing it.
	 *
	 * A static because it has to survive the level reload that carries it -
	 * every UObject in the world is destroyed in between, so there is nowhere
	 * else for it to live.
	 */
	static int32 ConsumePendingWaveSeed();

protected:
	/** Opens the current level again. The whole of both resets. */
	void ReloadLevel();

public:

	// ------------------------------------------------------------------
	// Ending the run
	// ------------------------------------------------------------------

	/** The King has fallen. Terminal. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Result")
	void NotifyKingDefeated();

	/** Every wave cleared and the field is empty. Terminal. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Result")
	void NotifyWavesCleared();

	UFUNCTION(BlueprintPure, Category = "PTK|Result")
	EPTKMatchResult GetMatchResult() const { return MatchResult; }

	UFUNCTION(BlueprintPure, Category = "PTK|Result")
	bool IsMatchOver() const { return MatchResult != EPTKMatchResult::InProgress; }

private:
	/** Shared tail of both endings: stop waves, stop spawners, freeze combat. */
	void EndRun(EPTKMatchResult Result);

	UPROPERTY(VisibleInstanceOnly, Category = "PTK|Start")
	bool bPlaying = false;

	UPROPERTY(VisibleInstanceOnly, Category = "PTK|Result")
	EPTKMatchResult MatchResult = EPTKMatchResult::InProgress;
};
