// Protect the King - 2D. Prototype combat HUD.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "PTKCombatHUD.generated.h"

class APTKBattlefield;
class APTKEnemyCharacter;
class APTKGuardBase;
class APTKGuardCharacter;
class APTKKingCharacter;
class APTKTopDownCharacter;
class APTKWaveManager;
class UTexture2D;

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
	 * Fells EVERY guard on the field, player-driven and AI alike.
	 *
	 * PTKGuardKill only reaches the pawn the player holds, which cannot test
	 * what happens when the whole line falls - the case the King fallback
	 * exists for.
	 */
	UFUNCTION(Exec)
	void PTKKillGuards(float Delay = 0.0f);

	/**
	 * Screenshot after Delay seconds, named king_<Name>.png.
	 *
	 * -ExecCmds all fire the instant the map loads, which is before the
	 * enemies have crossed the arena - so a capture worth looking at has to be
	 * able to wait.
	 */
	UFUNCTION(Exec)
	void PTKShot(float Delay = 0.0f, const FString& Name = TEXT("shot"));

	/**
	 * Presses the guard-select number key for a slot, Delay seconds from now.
	 *
	 * Deliberately injects the KEY rather than calling SelectGuardSlot, so a
	 * scripted run exercises the whole chain a player's finger does:
	 * IMC_PTK_GuardSwitch -> IA_SelectGuardN -> the controller's binding. A
	 * test that called the function directly would still pass with the mapping
	 * context missing, which is exactly the fault worth catching.
	 */
	UFUNCTION(Exec)
	void PTKSwitchKey(int32 Slot = 1, float Delay = 0.0f);

	/** Switches by calling the controller directly. Bypasses input - see above. */
	UFUNCTION(Exec)
	void PTKSwitchGuard(int32 Slot = 1, float Delay = 0.0f);

	/** Logs slot / health / driver / controller for all five guards. */
	UFUNCTION(Exec)
	void PTKGuards(float Delay = 0.0f);

	/** Kills one guard by slot, so the dead-guard rules can be tested. */
	UFUNCTION(Exec)
	void PTKKillSlot(int32 Slot = 1, float Delay = 0.0f);

	/**
	 * Holds a real keyboard key down for Hold seconds, Delay seconds from now.
	 *
	 * The same injection path as PTKSwitchKey, for the keys that are NOT part of
	 * switching: W to prove a newly possessed guard still steers, SpaceBar to
	 * prove it still swings, LeftShift to prove Aegis still braces. Calling
	 * SetMoveInput or StartAttack directly would prove none of those, because
	 * the AI uses those same entry points - only a key press proves the pawn's
	 * own Enhanced Input bindings came back with the possession.
	 */
	UFUNCTION(Exec)
	void PTKPressKey(const FString& KeyName = TEXT("W"), float Hold = 1.0f, float Delay = 0.0f);

	/**
	 * Aim rig: four stationary dummies exactly Up / Down / Left / Right of the
	 * played guard, then one shot in each direction.
	 *
	 * The field is cleared first and the dummies have their AI tick disabled,
	 * so nothing wanders into the line and nothing else can absorb a shot. A
	 * projectile that misses here missed because the collision line and the
	 * visible line disagree, which is the only thing this is measuring.
	 */
	UFUNCTION(Exec)
	void PTKAimTest(float Distance = 200.0f, float StartDelay = 2.0f);

	/**
	 * Splash rig: a tight cluster of dummies ahead of the played guard plus one
	 * far outside the blast, then a single shot into it.
	 */
	UFUNCTION(Exec)
	void PTKSplashTest(float Distance = 200.0f, float StartDelay = 2.0f);

	/** Jumps the wave system to a wave. Manual testing aid. */
	UFUNCTION(Exec)
	void PTKWave(int32 Wave = 1);

	/** Logs the wave phase, countdown and remaining enemy count. */
	UFUNCTION(Exec)
	void PTKWaveStatus();

	/** Damages a guard base by id, so base destruction can be driven manually. */
	UFUNCTION(Exec)
	void PTKBaseDamage(const FString& BaseName = TEXT("Aegis"), float Amount = 500.0f);

	/** Destroys a guard base outright. */
	UFUNCTION(Exec)
	void PTKBaseKill(const FString& BaseName = TEXT("Aegis"));

	/** Logs every base's health and destroyed state. */
	UFUNCTION(Exec)
	void PTKBases();

	/** Forces the King's emergency power, without having to wound him first. */
	UFUNCTION(Exec)
	void PTKKingPower();

	/** Logs what each enemy has chosen to attack and how far away it is. */
	UFUNCTION(Exec)
	void PTKTargets(int32 MaxLines = 12);

	/**
	 * Diagnostic: runs the melee overlap against a base and reports what the
	 * query returns, plus the nearest enemy's state and reach.
	 *
	 * Exists because "the base takes no damage" has several possible causes -
	 * the query missing it, the victim test rejecting it, or nothing ever
	 * getting close enough to swing - and they need telling apart.
	 */
	UFUNCTION(Exec)
	void PTKBaseProbe(const FString& BaseName = TEXT("Aegis"));

protected:
	/** Clears the field and returns the played guard, or null. */
	APTKTopDownCharacter* ClearFieldForRig();

	/** One stationary dummy at a world location. */
	AActor* SpawnDummy(const FVector& Where, const FString& Label);

	/** Logs every dummy's remaining health under a heading. */
	void LogDummies(const FString& Stage);

public:

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

	/**
	 * OFF by default now that the roster, wave panel and minimap carry the
	 * information a player actually needs. The per-enemy state dump was the
	 * prototype's readout and covers the top-left third of the screen; F1 still
	 * brings it back for debugging.
	 */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD")
	bool bShowDebugPanel = false;

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

	// ==================================================================
	// The real game HUD: roster, waves, minimap and warnings.
	//
	// All of it is canvas drawing, for the reason given at the top of this
	// file and for one more that matters at scale: the spec asks for a
	// minimap that shows hordes without a widget per enemy and without a
	// second rendered world. A canvas pass over a cached actor list is
	// exactly that - it costs one draw call per marker and needs no
	// SceneCapture, no render target and no widget tree.
	// ==================================================================

	/** Roster panel with all five guards, the King, and the selected highlight. */
	void DrawGuardRoster();

	/** Wave number, enemies remaining, and the intermission countdown. */
	void DrawWavePanel();

	/** The battlefield overview, top-right. */
	void DrawMinimap();

	/** One marker on the minimap, in minimap-local pixels. */
	void DrawMinimapMarker(const FVector2D& Centre, float Size,
		const FLinearColor& Colour, bool bDiamond = false);

	/** Enemies clustered into horde blips, so a swarm reads as one threat. */
	void DrawMinimapHordes(const FVector2D& Origin, const FVector2D& Size);

	/**
	 * Floating names above characters that have left their post.
	 *
	 * Hidden at home by design - a guard standing where it belongs needs no
	 * label, and five permanent nameplates would clutter the field the labels
	 * exist to clarify.
	 */
	void DrawWorldLabels();

	/** Under-attack and incoming-horde banners, rate limited. */
	void DrawWarnings();

	/** VICTORY / GAME OVER, once the run has ended. */
	void DrawResultBanner();

	/** Centred text helper: returns the width drawn. */
	float DrawCentredText(const FString& Text, float CentreX, float Y,
		const FLinearColor& Colour, float Scale = 1.0f);

	/** Panel background with a border, so text stays readable over the map. */
	void DrawPanel(float X, float Y, float W, float H, float Alpha = 0.55f);

	/** World point to minimap pixel. */
	FVector2D WorldToMinimap(const FVector& World, const FVector2D& Origin,
		const FVector2D& Size) const;

	const APTKBattlefield* GetBattlefield() const;
	APTKWaveManager* GetWaveManager() const;

	// ------------------------------------------------------------------
	// Layout
	// ------------------------------------------------------------------

	/** Minimap width as a fraction of the viewport, so it scales with the window. */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Minimap", meta = (ClampMin = "0.05", ClampMax = "0.5"))
	float MinimapWidthFraction = 0.19f;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Minimap")
	float MinimapMargin = 14.0f;

	/** Enemies within this world distance of each other become one blip. */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Minimap", meta = (ClampMin = "1.0"))
	float HordeClusterRadius = 420.0f;

	/**
	 * The battlefield art, drawn as the minimap background.
	 *
	 * Left unset by default and resolved on the first draw - see DrawMinimap.
	 * An asset assigned here wins and is never overwritten.
	 */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Minimap")
	TObjectPtr<UTexture2D> MinimapTexture;

	/** Latches after the first resolve attempt, successful or not. */
	bool bMinimapTextureResolved = false;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Roster")
	float RosterRowHeight = 22.0f;

	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Roster")
	float RosterWidth = 216.0f;

	/**
	 * How far a guard may drift from its post before its name appears.
	 * Roughly half a tile, as the spec asks.
	 */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Labels", meta = (ClampMin = "1.0"))
	float LabelHomeThreshold = 32.0f;

	/** Seconds a warning banner stays up once raised. */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Warnings", meta = (ClampMin = "0.1"))
	float WarningHoldTime = 2.5f;

	/** Minimum gap between two showings of the SAME warning. */
	UPROPERTY(EditDefaultsOnly, Category = "PTK|HUD|Warnings", meta = (ClampMin = "0.1"))
	float WarningCooldown = 6.0f;

private:
	/**
	 * Live warnings, keyed by text so the same message cannot queue twice.
	 *
	 * Keeping the cooldown per MESSAGE rather than one global timer is what
	 * lets "Aegis base under attack" and "King core under attack" both appear -
	 * they are different facts, and suppressing the second because the first
	 * was recent would hide the more urgent one.
	 */
	struct FWarningState
	{
		float ShownAt = 0.0f;
		float ExpiresAt = 0.0f;
	};
	TMap<FString, FWarningState> Warnings;

	/** Raises a warning if its cooldown has elapsed. */
	void RaiseWarning(const FString& Text);
};
