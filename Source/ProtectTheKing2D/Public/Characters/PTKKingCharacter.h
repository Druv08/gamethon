// Protect the King - 2D. The protected objective.

#pragma once

#include "CoreMinimal.h"
#include "Combat/PTKCombatTarget.h"
#include "Core/PTKTypes.h"
#include "GameFramework/Actor.h"
#include "PTKKingCharacter.generated.h"

class APTKGuardCharacter;
class UCapsuleComponent;
class UPaperFlipbook;
class UPaperFlipbookComponent;
class UPTKHealthComponent;

/**
 * APTKKingCharacter
 * =================
 * The King: a stationary, non-possessable objective that reacts but never
 * travels.
 *
 *
 * WHY THIS DERIVES FROM AActor AND NOT FROM APTKTopDownCharacter
 * --------------------------------------------------------------
 * The King must never walk, never be driven by WASD and never be possessed.
 * Those could be arranged on a Character by clearing input bindings and
 * disabling the movement component - but that is a configuration promise, and
 * configuration drifts: one stray DefaultPawnClass, one Blueprint that
 * re-enables movement, and the objective starts strolling around the arena.
 *
 * Deriving from AActor makes it structural instead. An AActor is not a Pawn,
 * so no PlayerController can possess it, there is no movement component to
 * re-enable and no input component to bind. "The King does not move" stops
 * being a setting that must be maintained and becomes a fact about the type.
 *
 * Everything genuinely shared is still shared: the same UPTKHealthComponent as
 * Ravager and Swarm Node, the same UPaperFlipbookComponent rendering, the same
 * engine damage pipeline, the same sprite-mirroring convention. What is NOT
 * inherited is the guard/player movement machinery, which he has no use for.
 *
 *
 * STATE MACHINE
 * -------------
 *   Idle  <-> Alert          steady; chosen purely by whether a living enemy
 *                            is inside AlertRadius
 *   PowerCast, Hit           timed; play once, then return to whichever of
 *                            Idle/Alert is correct at that moment
 *   Dead                     terminal; absorbs everything, and the body stays
 *
 * Alert is a reaction, not an attack. The King never fights back - he has no
 * attack state at all, by design.
 *
 * The real support ability (the 200% guard boost) is NOT implemented here.
 * TriggerPowerCast() plays the animation and nothing else; the gameplay effect
 * is a later phase and will hang off the same call.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKKingCharacter : public AActor, public IPTKCombatTarget
{
	GENERATED_BODY()

public:
	APTKKingCharacter();

	// --- IPTKCombatTarget ------------------------------------------
	//
	// This is the whole point of the interface: the King is attackable
	// without being a Pawn. He gains no movement, no controller and no
	// input by answering these three questions.
	virtual UPTKHealthComponent* GetCombatHealth() const override { return HealthComponent; }
	virtual EPTKTeam GetCombatTeam() const override { return Team; }
	virtual bool IsCombatDead() const override { return IsDead(); }

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintPure, Category = "PTK|King")
	UPTKHealthComponent* GetHealthComponent() const { return HealthComponent; }

	UFUNCTION(BlueprintPure, Category = "PTK|King")
	UPaperFlipbookComponent* GetSprite() const { return Sprite; }

	UFUNCTION(BlueprintPure, Category = "PTK|King")
	EPTKKingState GetKingState() const { return State; }

	UFUNCTION(BlueprintPure, Category = "PTK|King")
	EPTKTeam GetTeam() const { return Team; }

	UFUNCTION(BlueprintPure, Category = "PTK|King")
	bool IsDead() const { return State == EPTKKingState::Dead; }

	/** True while a living enemy is inside AlertRadius. */
	UFUNCTION(BlueprintPure, Category = "PTK|King")
	bool IsAlerted() const { return bEnemyNearby; }

	/**
	 * Plays the power cast once, then returns to Idle or Alert.
	 *
	 * Animation ONLY for this phase - it grants nothing. Ignored while dead,
	 * and ignored while a cast is already running so that spamming the trigger
	 * cannot restart the flipbook every frame and freeze it on frame 1.
	 *
	 * Returns true if a cast actually started.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|King")
	bool TriggerPowerCast();

	/**
	 * The emergency power: casts, picks one living guard, and boosts it.
	 *
	 * Fires by itself once the King's health crosses PowerHealthThreshold. It is
	 * a single desperate act, not a cooldown ability - bPowerSpent latches, so a
	 * King who is healed and wounded again does not get a second one.
	 *
	 * Returns true only if a guard was actually boosted.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|King|Power")
	bool TriggerEmergencyPower();

	UFUNCTION(BlueprintPure, Category = "PTK|King|Power")
	bool IsPowerSpent() const { return bPowerSpent; }

	/** The guard currently carrying the King's boost, or nullptr. */
	UFUNCTION(BlueprintPure, Category = "PTK|King|Power")
	APTKGuardCharacter* GetBoostedGuard() const;

	/** Development helper: applies damage through the normal health path. */
	UFUNCTION(BlueprintCallable, Category = "PTK|King|Debug")
	void DebugApplyDamage(float Amount);

	/**
	 * Development helper: changes the alert radius at runtime.
	 *
	 * Lets a test drive Idle <-> Alert in both directions against real enemy
	 * positions, instead of having to march enemies around the arena.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|King|Debug")
	void DebugSetAlertRadius(float NewRadius);

	/** Turns the health heartbeat on or off at runtime. */
	UFUNCTION(BlueprintCallable, Category = "PTK|King|Debug")
	void DebugSetHealthHeartbeat(bool bEnabled) { bLogHealthHeartbeat = bEnabled; HeartbeatTimer = 0.0f; }

protected:
	/** Root. Query-only so the King never physically obstructs the fight. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|King")
	TObjectPtr<UCapsuleComponent> Capsule;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|King")
	TObjectPtr<UPaperFlipbookComponent> Sprite;

	/** The same health component every other character uses. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|King")
	TObjectPtr<UPTKHealthComponent> HealthComponent;

	// ------------------------------------------------------------------
	// Animation
	// ------------------------------------------------------------------

	/** Loops forever while nothing is happening. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation")
	TObjectPtr<UPaperFlipbook> IdleFlipbook;

	/** Loops while an enemy is inside AlertRadius. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation")
	TObjectPtr<UPaperFlipbook> AlertFlipbook;

	/** Plays once per TriggerPowerCast(). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation")
	TObjectPtr<UPaperFlipbook> PowerCastFlipbook;

	/**
	 * Plays once when he takes damage.
	 *
	 * No dedicated hit sheet was supplied for the King, so this is left for
	 * whoever assigns real art later. While it is empty the Alert flipbook
	 * stands in - see ResolveHitFlipbook(). Nothing is fabricated.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation")
	TObjectPtr<UPaperFlipbook> HitFlipbook;

	/** Plays once on death and then holds on its final frame forever. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation")
	TObjectPtr<UPaperFlipbook> DeathFlipbook;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation", meta = (ClampMin = "0.01"))
	float IdlePlayRate = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation", meta = (ClampMin = "0.01"))
	float AlertPlayRate = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation", meta = (ClampMin = "0.01"))
	float PowerCastPlayRate = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation", meta = (ClampMin = "0.01"))
	float HitPlayRate = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation", meta = (ClampMin = "0.01"))
	float DeathPlayRate = 1.0f;

	// ------------------------------------------------------------------
	// Reaction tuning
	// ------------------------------------------------------------------

	/**
	 * How close a living enemy must come before the King reacts.
	 *
	 * Measured in world units on the XZ play plane. Generous by default: the
	 * point is to look aware of danger, not to be a trigger volume.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Alert", meta = (ClampMin = "0.0"))
	float AlertRadius = 600.0f;

	/**
	 * Seconds between proximity scans.
	 *
	 * The scan is an overlap query, so it is cheap - but it does not need to
	 * run at frame rate to decide whether the King looks worried, and a fixed
	 * interval keeps the cost flat however many enemies exist.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Alert", meta = (ClampMin = "0.02"))
	float AlertCheckInterval = 0.2f;

	/** Fallback duration used when a timed flipbook is missing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Animation", meta = (ClampMin = "0.05"))
	float FallbackStateDuration = 0.45f;

	// ------------------------------------------------------------------
	// Emergency power
	// ------------------------------------------------------------------

	/** Health fraction at or below which the King spends his power. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Power", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float PowerHealthThreshold = 0.35f;

	/** Combat multiplier granted to the chosen guard. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Power", meta = (ClampMin = "1.0"))
	float PowerBoostMultiplier = 2.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Power", meta = (ClampMin = "0.1"))
	float PowerBoostDuration = 10.0f;

	/** Latches on first use, so the power is once per run. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|King|Power")
	bool bPowerSpent = false;

	UPROPERTY()
	TObjectPtr<APTKGuardCharacter> BoostedGuard;

	/** Draws the alert radius in PIE. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Debug")
	bool bDrawAlertRadius = false;

	/**
	 * Periodic "still at N HP" line, for proving health does NOT move.
	 *
	 * OFF by default, so normal play logs only real damage events. It is a
	 * heartbeat, not a per-tick trace: absence of damage lines proves nothing
	 * to someone who suspects the logging itself is broken, whereas a steady
	 * 15000/15000 every few seconds is positive evidence.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Debug")
	bool bLogHealthHeartbeat = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Debug", meta = (ClampMin = "0.5"))
	float HealthHeartbeatInterval = 5.0f;

	// ------------------------------------------------------------------
	// Rendering
	// ------------------------------------------------------------------

	/**
	 * Same depth-sort rule the characters use, so the King composites with
	 * them correctly instead of always drawing in front or always behind.
	 *
	 * Must match APTKTopDownCharacter::DepthSortScale, or a guard standing
	 * level with the King would sort against a different scale and the two
	 * would swap over as they moved.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Rendering")
	bool bEnableDepthSorting = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Rendering", meta = (ClampMin = "0.0"))
	float DepthSortScale = 0.1f;

	/** His own side. See EPTKTeam::King. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|King")
	EPTKTeam Team = EPTKTeam::King;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Collision", meta = (ClampMin = "1.0"))
	float CollisionRadius = 22.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|King|Collision", meta = (ClampMin = "1.0"))
	float CollisionHalfHeight = 22.0f;

	// ------------------------------------------------------------------
	// Runtime
	// ------------------------------------------------------------------

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|King")
	EPTKKingState State = EPTKKingState::Idle;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|King")
	bool bEnemyNearby = false;

	/** Seconds left of a timed state (PowerCast / Hit). Zero when steady. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|King")
	float StateTimeRemaining = 0.0f;

	float AlertScanTimer = 0.0f;
	float HeartbeatTimer = 0.0f;

	/** Where the King stood at BeginPlay. Re-asserted every tick. */
	FVector AnchorLocation = FVector::ZeroVector;

	/** Idle or Alert, whichever the current surroundings call for. */
	EPTKKingState SteadyState() const;

	/** Switches state and pushes the matching flipbook. */
	void EnterState(EPTKKingState NewState);

	/** Flipbook + play rate for a state, or nullptr when unassigned. */
	UPaperFlipbook* FlipbookForState(EPTKKingState Query, float& OutRate) const;

	/** HitFlipbook if one was assigned, otherwise the Alert stand-in. */
	UPaperFlipbook* ResolveHitFlipbook() const;

	/** Overlap query for living enemies inside AlertRadius. */
	void ScanForNearbyEnemies();

	UFUNCTION()
	void HandleHealthChanged(UPTKHealthComponent* Component, float NewHealth,
		float Delta, AActor* DamageInstigator);

	UFUNCTION()
	void HandleDeath(UPTKHealthComponent* Component, AActor* Killer);
};
