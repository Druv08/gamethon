// Protect the King - 2D. Base game mode.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "PTKGameModeBase.generated.h"

/**
 * APTKGameModeBase
 * ================
 * Owns the one-way WaitingToStart -> Playing transition in the gameplay map.
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

	static bool IsGameplayActive(const UWorld* World);

private:
	UPROPERTY(VisibleInstanceOnly, Category = "PTK|Start")
	bool bPlaying = false;
};
