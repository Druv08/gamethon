// Protect the King - 2D. Prototype combat HUD.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "PTKCombatHUD.generated.h"

class APTKEnemyCharacter;
class APTKKingCharacter;
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

	// ------------------------------------------------------------------
	// Development console commands
	//
	// These live on the HUD rather than on the King because the console only
	// dispatches exec functions to objects already in the input chain - the
	// PlayerController, its Pawn, the GameMode and the HUD. Putting them here
	// means the King needs no input component and no player binding, so the
	// prototype can drive him without ever attaching him to normal controls.
	//
	//     PTKKingCast              play the power cast once
	//     PTKKingDamage <amount>   apply damage through the shared health path
	//     PTKKingKill              apply enough damage to finish him
	// ------------------------------------------------------------------

	UFUNCTION(Exec)
	void PTKKingCast();

	UFUNCTION(Exec)
	void PTKKingDamage(float Amount = 500.0f);

	UFUNCTION(Exec)
	void PTKKingKill();

	UFUNCTION(Exec)
	void PTKKingAlertRadius(float Radius = 600.0f);

	virtual void BeginPlay() override;

protected:
	/** Draws a labelled bar with a border. Fraction is clamped to 0..1. */
	void DrawBar(float X, float Y, float Width, float Height,
		float Fraction, const FLinearColor& Fill);

	/** Player bar plus name and numbers, anchored to the bottom-left. */
	void DrawPlayerPanel(APTKTopDownCharacter* Player);

	/** Floating bar above one enemy, projected from its world position. */
	void DrawEnemyBar(APTKEnemyCharacter* Enemy);

	/** King bar plus state, anchored top-centre - he is the objective. */
	void DrawKingPanel(APTKKingCharacter* King);

	/** The one King in the level, or nullptr. */
	APTKKingCharacter* FindKing() const;

	// ------------------------------------------------------------------
	// Scripted PIE check, enabled with -ptkkingtest on the command line.
	//
	// Prototype scaffolding, deliberately parked in the prototype HUD rather
	// than in APTKKingCharacter: the King should not carry test code, and this
	// whole class is already marked for replacement. Without the switch none
	// of it runs and no timer is ever registered.
	//
	// It drives one deterministic pass over every King state - cast, hit,
	// repeated hit, death, damage-after-death - so a single run proves the
	// state machine instead of needing a human at the keyboard.
	// ------------------------------------------------------------------

	/** Logs the King's state, health and position under a step label. */
	void LogKingStatus(const FString& Stage);

	/** Registers the timed sequence. */
	void StartKingSelfTest();

	/**
	 * Logs the structural facts behind "the King ignores movement input".
	 *
	 * Position staying still proves nothing on its own when no key was
	 * pressed. What does prove it is that he is not a Pawn, is not the
	 * possessed pawn, has no controller and has no input component - an actor
	 * with none of those cannot receive a movement binding at all.
	 */
	void LogKingInputIsolation();

	/** State / facing / distance / cooldown readout for everything alive. */
	void DrawDebugPanel(APTKTopDownCharacter* Player);

	/** Centred banner shown once the player is dead. */
	void DrawDefeatBanner();

	/** Centred banner shown once the King is dead. */
	void DrawKingDefeatBanner();

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

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float KingBarWidth = 320.0f;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	float KingBarHeight = 16.0f;
};
