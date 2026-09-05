// Protect the King - 2D. Player-controlled guard tier.

#pragma once

#include "CoreMinimal.h"
#include "Characters/PTKTopDownCharacter.h"
#include "PTKGuardCharacter.generated.h"

/**
 * APTKGuardCharacter
 * ==================
 * Shared base for the player-controlled defenders:
 * Ravager, Aegis, Wraith, Reaver and Sentinel.
 *
 * It deliberately adds almost nothing in Phase 1. All movement, facing and
 * animation behaviour lives in APTKTopDownCharacter, so a new guard is
 * created by making a Blueprint of this class and filling in flipbooks,
 * speed and collision - never by writing new movement code.
 *
 * This tier exists so that guard-only systems added later (ability slots,
 * guard switching, King proximity bonuses) have one obvious home that enemy
 * characters do not inherit.
 */
UCLASS(Abstract, Blueprintable)
class PROTECTTHEKING2D_API APTKGuardCharacter : public APTKTopDownCharacter
{
	GENERATED_BODY()

public:
	APTKGuardCharacter(const FObjectInitializer& ObjectInitializer);

	/** Stable lookup id, e.g. "Ravager". Used by future selection/HUD systems. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard")
	FName GetGuardId() const { return GuardId; }

	UFUNCTION(BlueprintPure, Category = "PTK|Guard")
	FText GetGuardDisplayName() const { return GuardDisplayName; }

protected:
	/** Stable internal id. Set once per guard Blueprint; never localise this. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Guard")
	FName GuardId = NAME_None;

	/** Player-facing name. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Guard")
	FText GuardDisplayName;
};
