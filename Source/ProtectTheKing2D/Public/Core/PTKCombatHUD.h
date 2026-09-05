// Protect the King - 2D. Prototype combat HUD.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "PTKCombatHUD.generated.h"

class APTKEnemyCharacter;
class APTKTopDownCharacter;

/**
 * APTKCombatHUD
 * =============
 * Health bars for the combat prototype, drawn straight onto the canvas.
 *
 * This is NOT the game's HUD. It exists to make the fight readable while the
 * combat systems are being proven, and it is expected to be replaced wholesale
 * by a real UMG interface later.
 *
 * Canvas drawing was chosen over UMG deliberately. A UMG bar needs a widget
 * Blueprint, a widget component per enemy and a binding for each value - three
 * assets and a Blueprint graph to show two numbers. AHUD::DrawHUD needs none of
 * that: it is pure C++, has no assets to keep in sync, cannot break through an
 * asset re-import, and works identically with Paper2D because it draws after
 * the scene rather than in it.
 *
 * The player's bar is anchored to the screen. Enemy bars are projected from
 * world space so they float above each creature.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKCombatHUD : public AHUD
{
	GENERATED_BODY()

public:
	APTKCombatHUD();

	virtual void DrawHUD() override;

	/** Toggles the per-character diagnostic block. Bound to F1 by the pawn. */
	UFUNCTION(BlueprintCallable, Category = "PTK|HUD")
	void ToggleDebugPanel() { bShowDebugPanel = !bShowDebugPanel; }

protected:
	/** Draws a labelled bar with a border. Fraction is clamped to 0..1. */
	void DrawBar(float X, float Y, float Width, float Height,
		float Fraction, const FLinearColor& Fill);

	/** Player bar plus name and numbers, anchored to the bottom-left. */
	void DrawPlayerPanel(APTKTopDownCharacter* Player);

	/** Floating bar above one enemy, projected from its world position. */
	void DrawEnemyBar(APTKEnemyCharacter* Enemy);

	/** State / facing / distance / cooldown readout for everything alive. */
	void DrawDebugPanel(APTKTopDownCharacter* Player);

	/** Centred banner shown once the player is dead. */
	void DrawDefeatBanner();

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	bool bShowDebugPanel = true;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float PlayerBarWidth = 280.0f;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float PlayerBarHeight = 18.0f;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float EnemyBarWidth = 64.0f;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float EnemyBarHeight = 7.0f;

	/** World units above the enemy's origin to float its bar. */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float EnemyBarWorldOffset = 110.0f;
};
