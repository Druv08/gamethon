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
 *
 *
 * WHY THE AI TUNING LIVES HERE AND NOT ON THE CONTROLLER
 * -----------------------------------------------------
 * A guard defends a POST, and which post it holds and how far it will stray
 * from it are properties of the guard, not of whatever happens to be driving it
 * this second. Keeping them on the character means each Blueprint tunes its own
 * area, and - the part that matters for switching - they survive the controller
 * being swapped. A guard the player takes over and later releases resumes
 * defending the same ground, because the ground was never the controller's to
 * remember.
 *
 * See APTKGuardAIController for the behaviour that reads them.
 */
UCLASS(Abstract, Blueprintable)
class PROTECTTHEKING2D_API APTKGuardCharacter : public APTKTopDownCharacter
{
	GENERATED_BODY()

public:
	APTKGuardCharacter(const FObjectInitializer& ObjectInitializer);

	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;

	/**
	 * The post this guard defends - where it stands when nothing is happening.
	 *
	 * Captured from wherever the guard was placed or spawned, so a designer sets
	 * it by dragging the actor rather than by editing a number.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	FVector GetHomePosition() const { return HomePosition; }

	UFUNCTION(BlueprintCallable, Category = "PTK|Guard|AI")
	void SetHomePosition(const FVector& NewHome) { HomePosition = NewHome; }

protected:
	/** Records where this guard stands as its post, unless one was authored. */
	void CaptureHomePosition();

public:

	/** How far this guard notices an enemy from. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	float GetDetectionRange() const { return GuardDetectionRange; }

	/** How far from home an enemy may be dragged before the guard gives up. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	float GetMaxChaseDistance() const { return MaxChaseDistance; }

	/**
	 * Fraction of the guard's own attack reach at which it stops closing.
	 *
	 * This one number is what makes a mage fight like a mage without a line of
	 * per-guard AI code: the AI approaches until it is inside AttackReach *
	 * this, and reach is already 3.5 tiles for the melee guards and 6-7 for the
	 * ranged ones. Ravager walks into a swarm; Wraith stops 350 units short.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	float GetAIEngageFraction() const { return AIEngageFraction; }

	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	float GetAIHomeTolerance() const { return AIHomeTolerance; }

	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	int32 GetAIDefendMinEnemies() const { return AIDefendMinEnemies; }

	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	float GetAIDefendCooldown() const { return AIDefendCooldown; }

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

	// ------------------------------------------------------------------
	// AI tuning - read by APTKGuardAIController, ignored while the player
	// is driving. Every one of these is editable per guard Blueprint.
	// ------------------------------------------------------------------

	/** Set from the actor's own location at BeginPlay unless already assigned. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI")
	FVector HomePosition = FVector::ZeroVector;

	/** How far away an enemy is noticed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "0.0"))
	float GuardDetectionRange = 600.0f;

	/**
	 * How far from HOME an enemy may get before this guard disengages.
	 *
	 * This is measured from the post, not from the guard, and that is the whole
	 * point: it bounds the area rather than the pursuit, so a guard cannot be
	 * walked across the map by an enemy that keeps retreating one step.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "0.0"))
	float MaxChaseDistance = 400.0f;

	/** Stop closing at this fraction of AttackReach. See GetAIEngageFraction. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "0.1", ClampMax = "1.0"))
	float AIEngageFraction = 0.8f;

	/** Close enough to home to count as arrived, so the guard stops fidgeting. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "1.0"))
	float AIHomeTolerance = 40.0f;

	/**
	 * How many enemies must be in reach before the AI raises a shield.
	 *
	 * Only a guard with defence art can do this at all - StartDefend refuses
	 * without it - so this is Aegis's number and costs the others nothing.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "1"))
	int32 AIDefendMinEnemies = 3;

	/**
	 * Seconds between AI-triggered blocks.
	 *
	 * Without it the AI would raise the shield again the instant it dropped and
	 * be permanently invulnerable - the block absorbs everything while it is up,
	 * so back-to-back blocks are not a tactic, they are immortality.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "0.0"))
	float AIDefendCooldown = 6.0f;
};
