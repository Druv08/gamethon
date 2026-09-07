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
