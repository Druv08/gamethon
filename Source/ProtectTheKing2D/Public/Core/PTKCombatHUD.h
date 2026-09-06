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

	/**
	 * Runs the scripted King check. TYPE IT YOURSELF - nothing calls this.
	 *
	 * It deliberately damages and then KILLS the King, so it is a console
	 * command and nothing else: no BeginPlay hook, no command-line switch, no
	 * timer registered until the moment someone types PTKKingTest.
	 */
	UFUNCTION(Exec)
	void PTKKingTest();

	/**
	 * Makes the player character swing, so the guard's multi-target arc can be
	 * exercised without a human at the keyboard. Manual only.
	 *
	 * StartDelay exists because enemies begin the match across the arena: a
	 * swing fired the instant the level loads connects with nothing and proves
	 * nothing.
	 */
	UFUNCTION(Exec)
	void PTKGuardAttack(int32 Count = 1, float Interval = 1.2f, float StartDelay = 0.0f);

	/**
	 * Feeds movement input to the played guard for Duration seconds.
	 *
	 * X = screen right, Y = screen up, so (0,-1) walks down the screen. Goes
	 * through SetMoveInput, which is the same path the player's own input
	 * takes - this drives the character, it does not simulate around it.
	 * Manual only; exists so all four directional cycles can be checked
	 * without a human holding a key.
	 */
	UFUNCTION(Exec)
	void PTKGuardMove(float X, float Y, float Duration = 2.0f, float StartDelay = 0.0f);

	/** Turns the King's health heartbeat on (1) or off (0). */
	UFUNCTION(Exec)
	void PTKKingHeartbeat(int32 bEnabled = 1);

	/**
	 * Swaps the played character to another guard Blueprint. Manual only.
	 *
	 * Guard switching is a later phase; this is the smallest thing that can
	 * prove a new guard actually plays. It spawns the requested guard where the
	 * current one stands, possesses it, and removes the old one so exactly one
	 * living guard remains - which keeps enemy targeting unambiguous.
	 *
	 * Nothing about the GameMode or DefaultPawnClass is touched, so the next
	 * Play starts as Ravager exactly as before.
	 */
	UFUNCTION(Exec)
	void PTKPlayGuard(const FString& GuardName = TEXT("Aegis"));

	/** Kills the player guard outright, to test what the enemies do next. */
	/**
	 * Raises the played guard's shield, `Count` times, `Interval` apart.
	 *
	 * The same entry point the Defend key uses, so a scripted test exercises the
	 * real skill rather than a parallel one. Does nothing for a guard with no
	 * defence art.
	 */
	UFUNCTION(Exec)
	void PTKGuardDefend(int32 Count = 1, float Interval = 1.5f, float StartDelay = 0.0f);

	UFUNCTION(Exec)
	void PTKGuardKill(float Delay = 0.0f);

	/**
	 * Screenshot after Delay seconds, named king_<Name>.png.
	 *
	 * -ExecCmds all fire the instant the map loads, which is before the
	 * enemies have crossed the arena - so a capture worth looking at has to be
	 * able to wait.
	 */
	UFUNCTION(Exec)
	void PTKShot(float Delay = 0.0f, const FString& Name = TEXT("shot"));

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
	// Scripted King check. MANUAL ONLY - reached solely by typing
	// PTKKingTest at the console.
	//
	// It was previously armed from BeginPlay whenever -ptkkingtest appeared on
	// the command line. That was a mistake: FCommandLine is process-global and
	// survives for the whole editor session, so once the flag was present
	// EVERY subsequent Play ran a sequence that damages and kills the King -
	// which looked exactly like the King losing health on his own. A routine
	// that deals damage must never be reachable from BeginPlay.
	// ------------------------------------------------------------------

	/** Logs the King's state, health and position under a step label. */
	void LogKingStatus(const FString& Stage);

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
	/** Name of the guard currently being played, upper-cased for the panel. */
	FString PlayerLabel(APTKTopDownCharacter* Player) const;

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
