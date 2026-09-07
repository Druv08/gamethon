// Protect the King - 2D. The one guard AI.

#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "Core/PTKTypes.h"
#include "PTKGuardAIController.generated.h"

class APTKGuardCharacter;

/**
 * APTKGuardAIController
 * =====================
 * Drives ANY APTKGuardCharacter that the player is not currently driving.
 *
 * One controller for all five guards. There is no Aegis AI, no Wraith AI and no
 * Sentinel AI - a mage fights like a mage because of what its own Blueprint
 * already says about it, not because of a branch in here:
 *
 *   how far it closes    AttackRangeTiles x AIEngageFraction
 *                        3.5 tiles for the melee guards, 6-7 for the ranged
 *                        ones, so Reaver walks into the crowd and Wraith stops
 *                        350 units short of it
 *   what its blow does   StartAttack(), which is the melee sphere for Ravager,
 *                        Aegis and Reaver and a projectile for Wraith and
 *                        Sentinel, decided by ProjectileClass
 *   whether it blocks    StartDefend(), which refuses outright without defence
 *                        art - so only Aegis ever does
 *   what it defends      the guard's own HomePosition and MaxChaseDistance
 *
 * Adding a sixth guard therefore needs no AI work at all.
 *
 *
 * IT DRIVES THE PAWN THROUGH THE PLAYER'S OWN ENTRY POINTS
 * --------------------------------------------------------
 * SetMoveInput(), StartAttack() and StartDefend() are exactly what the Enhanced
 * Input handlers call. Nothing here reaches past them into movement, facing or
 * animation, which is why an AI guard walks, turns, swings and dies identically
 * to a player-driven one without a second copy of any of it.
 *
 *
 * CONTROL IS EXCLUSIVE, AND THAT IS THE POINT
 * -------------------------------------------
 * A pawn has exactly one controller in Unreal, so a guard is either possessed
 * by this or by the PlayerController - never both, structurally rather than by
 * agreement. GetAIState() returns Inactive when this controller holds nothing.
 *
 * That is what makes switching a later, small job. The flow will be:
 *
 *     PlayerController->Possess(NewGuard)     the guard's AI controller is
 *                                             detached automatically
 *     SpawnAIFor(OldGuard)  or  ResumeAI()    the guard the player left goes
 *                                             back to its post
 *
 * Nothing in this class needs to change for that: HomePosition lives on the
 * character, so a guard that is handed back remembers the ground it holds, and
 * SetAIEnabled() exists so control can be suspended without unpossessing.
 * Switching itself is deliberately NOT implemented yet.
 *
 *
 * WHY NO BEHAVIOR TREE
 * --------------------
 * The same reasoning as APTKEnemyCharacter: this is five states driven by two
 * distance checks. A tree, blackboard and navmesh would turn "why did it not
 * attack" into an asset hunt. Steering is direct - the arena is open and there
 * is no path system to respect yet.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKGuardAIController : public AAIController
{
	GENERATED_BODY()

public:
	APTKGuardAIController();

	virtual void Tick(float DeltaSeconds) override;
	virtual void OnPossess(APawn* InPawn) override;
	virtual void OnUnPossess() override;

	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	EPTKGuardAIState GetAIState() const { return AIState; }

	/** Whatever this guard is currently fighting, or null. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	AActor* GetTarget() const { return Target; }

	/**
	 * Suspends or resumes the behaviour without giving up the pawn.
	 *
	 * Not used yet. It exists because guard switching will want to stop a
	 * guard thinking for a moment without tearing down and rebuilding its
	 * controller.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Guard|AI")
	void SetAIEnabled(bool bEnabled);

	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	bool IsAIEnabled() const { return bAIEnabled; }

	/** The ally or base this guard has gone to help, or null. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|AI")
	AActor* GetAssistTarget() const { return AssistTarget; }

protected:
	/** Nearest living hostile that is inside this guard's defended area. */
	AActor* FindTarget(const APTKGuardCharacter* Guard) const;

	/**
	 * The point this guard is currently defending.
	 *
	 * Its own post normally; the ally it is helping while assisting. Target
	 * search and the leash are both measured from HERE rather than from
	 * HomePosition, which is what lets a guard that has travelled to a fight
	 * actually engage in it - anchoring to home would send it across the map
	 * and then leave it standing there unable to see anything.
	 */
	FVector GetDefendAnchor(const APTKGuardCharacter* Guard) const;

	/**
	 * A neighbouring guard or base worth leaving the post for, or null.
	 *
	 * Refuses a threat that already has MaxAssistGuardsPerThreat helpers, which
	 * is what stops the whole line dogpiling one skirmish and leaving every
	 * other lane open.
	 */
	AActor* FindAssistTarget(const APTKGuardCharacter* Guard) const;

	/** How many OTHER guards are already assisting this threat. */
	int32 CountAssistersOn(const AActor* Threat) const;

	/** True while a guard or base is being meaningfully attacked. */
	bool IsThreatened(const AActor* Candidate) const;

	/** True while the target is alive, hostile, and still worth holding. */
	bool IsTargetStillValid(const APTKGuardCharacter* Guard, const AActor* Candidate) const;

	/** How many hostiles are within Radius of the guard. */
	int32 CountHostilesWithin(const APTKGuardCharacter* Guard, float Radius) const;

	/** A world offset expressed in the character's screen basis, clamped to 1. */
	FVector2D ToScreenInput(const APTKGuardCharacter* Guard, const FVector& WorldOffset) const;

	/** Points the guard at a world location without moving it. */
	void FaceLocation(APTKGuardCharacter* Guard, const FVector& Where) const;

	/** Only Aegis passes this - StartDefend refuses without defence art. */
	void ConsiderDefending(APTKGuardCharacter* Guard, float DeltaSeconds);

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Guard|AI")
	EPTKGuardAIState AIState = EPTKGuardAIState::Inactive;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Guard|AI")
	TObjectPtr<AActor> Target;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Guard|AI")
	TObjectPtr<AActor> AssistTarget;

	// ------------------------------------------------------------------
	// Assist tuning
	// ------------------------------------------------------------------

	/** How far this guard will travel from its post to help. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|Assist", meta = (ClampMin = "0.0"))
	float AssistRadius = 1600.0f;

	/**
	 * How many hostiles must be on an ally or base before it counts as needing
	 * help. One wandering Swarm Node is not an emergency; three is.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|Assist", meta = (ClampMin = "1"))
	int32 AssistThreatThreshold = 3;

	/** Ceiling on helpers per threat, so the line cannot dogpile. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|Assist", meta = (ClampMin = "1"))
	int32 MaxAssistGuardsPerThreat = 2;

	/** Radius around a threatened ally that counts as "the fight". */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|Assist", meta = (ClampMin = "1.0"))
	float AssistFightRadius = 700.0f;

	/** A guard below this health fraction stays home rather than going to help. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|Assist", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AssistMinHealthFraction = 0.35f;

	/** Seconds between assist scans. Cheaper and steadier than every frame. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|Assist", meta = (ClampMin = "0.05"))
	float AssistRefreshInterval = 0.75f;

	/**
	 * Seconds between target searches.
	 *
	 * Scanning every actor every frame for every guard is the one thing here
	 * that would actually cost something, and a guard that notices an enemy a
	 * fifth of a second late is indistinguishable from one that does not.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Guard|AI", meta = (ClampMin = "0.0"))
	float TargetRefreshInterval = 0.2f;

	/** Draws the detection and chase circles. Prototype aid only. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadWrite, Category = "PTK|Debug")
	bool bDrawAIRanges = false;

private:
	float TargetRefreshTimer = 0.0f;
	float AssistRefreshTimer = 0.0f;
	float DefendCooldownRemaining = 0.0f;
	bool bAIEnabled = true;
	EPTKGuardAIState LoggedState = EPTKGuardAIState::Inactive;
};
