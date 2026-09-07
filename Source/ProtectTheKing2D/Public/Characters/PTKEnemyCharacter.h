// Protect the King - 2D. Autonomous enemy tier.

#pragma once

#include "CoreMinimal.h"
#include "Characters/PTKTopDownCharacter.h"
#include "PTKEnemyCharacter.generated.h"

/**
 * APTKEnemyCharacter
 * ==================
 * Shared base for every autonomous enemy: Swarm Node, Infiltrator, Hijacker,
 * Encrypter, Exfiltrator.
 *
 * Everything visual and physical - movement, facing, flipbooks, health, melee
 * timing, death - is inherited from APTKTopDownCharacter unchanged. This class
 * adds exactly one thing: something to drive the input that a player would
 * otherwise supply. It feeds SetMoveInput() and StartAttack(), the same two
 * entry points the player's Enhanced Input handlers use, which is why an enemy
 * animates, faces and fights identically to a guard without duplicating any of
 * that code.
 *
 *
 * WHY THERE IS NO BEHAVIOR TREE
 * -----------------------------
 * The decision logic is a four-state machine driven by one distance check:
 *
 *     Idle  --target within DetectionRange-->  Chase
 *     Chase --target within AttackRange----->  Attack
 *     Attack--recovery elapsed-------------->  Chase
 *     any   --health reaches zero----------->  Dead
 *
 * A Behavior Tree, blackboard and EQS would add three assets and a navmesh
 * dependency to express that, and would make "why did it not attack" a
 * debugging session instead of a breakpoint. The real adaptive AI is a later
 * phase and can bring its own machinery; this exists to prove combat works.
 *
 * Movement is direct steering toward the target, not pathfinding. The arena is
 * open and the final lane/path system does not exist yet. When it does, only
 * ComputeDesiredInput() needs to change.
 */
UCLASS(Abstract, Blueprintable)
class PROTECTTHEKING2D_API APTKEnemyCharacter : public APTKTopDownCharacter
{
	GENERATED_BODY()

public:
	APTKEnemyCharacter(const FObjectInitializer& ObjectInitializer);

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintPure, Category = "PTK|Enemy")
	EPTKEnemyState GetEnemyState() const { return EnemyState; }

	/**
	 * Whatever this enemy is currently trying to kill.
	 *
	 * An AActor, not a character: the King is a valid target and is not a
	 * Pawn. Everything the AI needs from it comes through IPTKCombatTarget or
	 * from AActor itself.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Enemy")
	AActor* GetTarget() const { return Target; }

	/**
	 * An enemy damages the one character it chose to attack, and nobody else.
	 *
	 * The inherited sphere is a proximity test, not an intent test: on its own
	 * it damages every hostile body inside the arc, so a Swarm Node swinging
	 * at the player would also injure whatever else happened to be standing
	 * there. Requiring Victim == Target makes the swing mean what the AI
	 * decided it meant.
	 */
	virtual bool IsValidAttackVictim(const AActor* Victim) const override;

	/** Distance to the current target, or -1 when there is none. */
	UFUNCTION(BlueprintPure, Category = "PTK|Enemy")
	float GetDistanceToTarget() const;

	UFUNCTION(BlueprintPure, Category = "PTK|Enemy")
	float GetAttackCooldownRemaining() const { return AttackCooldownRemaining; }

	/** Stable id for HUD and logging, e.g. "SwarmNode". */
	UFUNCTION(BlueprintPure, Category = "PTK|Enemy")
	FName GetEnemyId() const { return EnemyId; }

	UFUNCTION(BlueprintPure, Category = "PTK|Enemy")
	FText GetEnemyDisplayName() const { return EnemyDisplayName; }

protected:
	virtual void HandleDeath(AActor* Killer) override;
	virtual void FireProjectile() override;

	/**
	 * Picks a target. Currently the player pawn, if it is hostile and alive.
	 *
	 * Deliberately not a threat table or a King/guard selection: this phase is
	 * one enemy against one player, and guessing at the later targeting rules
	 * would be work thrown away.
	 */
	virtual AActor* FindTarget() const;

	/**
	 * Screen-space movement input for this frame, in the same convention the
	 * player's IA_Move produces: X = screen right, Y = screen up, magnitude
	 * clamped to 1.
	 *
	 * Override this to add pathing or lane restrictions later; nothing else in
	 * the class needs to know how the direction was chosen.
	 */
	virtual FVector2D ComputeDesiredInput(const FVector& TargetLocation) const;

	/** Pure direction to the target, without crowd avoidance. Drives facing. */
	FVector2D ComputeBearingTo(const FVector& TargetLocation) const;

	/** Combined push away from nearby enemies. Zero when nobody is close. */
	FVector2D ComputeSeparation() const;

	/** Projects a world offset onto the screen basis. */
	FVector2D ToScreenSpace(const FVector& WorldOffset) const;

	/** Stable internal id. Set once per enemy Blueprint; never localise this. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Enemy")
	FName EnemyId = NAME_None;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Enemy")
	FText EnemyDisplayName;

	// ------------------------------------------------------------------
	// Perception
	// ------------------------------------------------------------------

	/**
	 * How close the target must come before this enemy wakes up.
	 *
	 * A plain radius, not line of sight: the test arena has no cover worth
	 * occluding against, and a sight check would only add a failure mode.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Perception", meta = (ClampMin = "0.0"))
	float DetectionRange = 800.0f;

	/*
	 * There is deliberately no separate AttackRange here. The distance at which
	 * the enemy stops and starts swinging is GetAttackReach() - the same number
	 * that sizes its melee sphere - so the two can never drift apart and leave
	 * an enemy halting just outside its own reach, swinging at nothing.
	 * Tune it through AttackRangeTiles on the base class.
	 */

	/**
	 * Extra distance the target may drift before the enemy gives chase again.
	 *
	 * Without this margin a target hovering exactly on AttackRange would flip
	 * between Chase and Attack every frame.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Perception", meta = (ClampMin = "0.0"))
	float AttackRangeTolerance = 25.0f;

	/**
	 * Seconds between target searches. The target rarely changes, so resolving
	 * it every frame would be wasted work.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Perception", meta = (ClampMin = "0.0"))
	float TargetRefreshInterval = 0.5f;

	// ------------------------------------------------------------------
	// Attack pacing
	// ------------------------------------------------------------------

	/**
	 * Recovery after a swing finishes, before another may start.
	 *
	 * This is a pause between attacks, not a damage limiter - a single swing
	 * already deals damage exactly once (see AttackHitActors on the base class).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Combat", meta = (ClampMin = "0.0"))
	float AttackCooldown = 1.2f;

	/** Randomises the first attack so several enemies never swing in lockstep. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Combat", meta = (ClampMin = "0.0"))
	float InitialAttackDelay = 0.4f;

	// ------------------------------------------------------------------
	// Crowd
	//
	// The minimum needed to stop ten enemies collapsing onto one point and
	// jamming each other. This is NOT flocking - there is no alignment and no
	// cohesion, only a short-range push apart.
	// ------------------------------------------------------------------

	/** Enemies closer than this push each other apart. 0 disables separation. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Crowd", meta = (ClampMin = "0.0"))
	float SeparationRadius = 55.0f;

	/**
	 * How hard separation competes with chasing.
	 *
	 * Below 1 the pull toward the target always wins in the end, so a crowd
	 * still closes in and surrounds rather than milling about at arm's length.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Enemy|Crowd", meta = (ClampMin = "0.0", ClampMax = "2.0"))
	float SeparationWeight = 0.65f;

	// ------------------------------------------------------------------
	// Debug
	// ------------------------------------------------------------------

	/** Draws detection and attack radii in the world. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Debug")
	bool bDrawPerceptionRanges = false;

	// ------------------------------------------------------------------
	// Runtime state
	// ------------------------------------------------------------------

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Enemy")
	EPTKEnemyState EnemyState = EPTKEnemyState::Idle;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Enemy")
	TObjectPtr<AActor> Target;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Enemy")
	float AttackCooldownRemaining = 0.0f;

	float TargetRefreshTimer = 0.0f;

	/** Throttles the once-a-second AI diagnostic line. */
	float DiagnosticTimer = 0.0f;
};
