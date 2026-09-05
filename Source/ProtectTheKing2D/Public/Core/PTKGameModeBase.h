// Protect the King - 2D. Base game mode.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "PTKGameModeBase.generated.h"

/**
 * APTKGameModeBase
 * ================
 * Minimal game mode for the Phase 1 movement prototype.
 *
 * It only resolves a default pawn. Round logic, wave spawning, scoring and
 * the King objective are explicitly out of scope until movement is signed off.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKGameModeBase : public AGameModeBase
{
	GENERATED_BODY()

public:
	APTKGameModeBase();
};
