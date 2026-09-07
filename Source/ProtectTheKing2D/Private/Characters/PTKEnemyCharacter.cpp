// Protect the King - 2D. Autonomous enemy tier.

#include "Characters/PTKEnemyCharacter.h"

#include "AIController.h"
#include "Characters/PTKGuardCharacter.h"
#include "Characters/PTKKingCharacter.h"
#include "Combat/PTKCombatTarget.h"
#include "Combat/PTKProjectile.h"
#include "Core/PTKBattlefield.h"
#include "Core/PTKGuardBase.h"
#include "EngineUtils.h"
#include "Components/CapsuleComponent.h"
#include "Components/PTKHealthComponent.h"
#include "DrawDebugHelpers.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/OverlapResult.h"
#include "Kismet/GameplayStatics.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKEnemyCharacter)

APTKEnemyCharacter::APTKEnemyCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	Team = EPTKTeam::Enemies;

	// ENEMY SCALE. Individually fragile and short-reaching; the threat comes
	// from numbers. Each enemy type sets its own MaxHealth in its Blueprint -
	// this is only the tier default.
	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(100.0f);
	}

	// One tile of reach, against a guard's 3.5. The enemy must close almost all
	// the way in before it can hit back.
	AttackRangeTiles = 1.0f;
	AttackHitWidthFactor = 0.45f;
	AttackDamage = 15.0f;

	// A Swarm Node bites one thing at a time. Only the guard's axe sweeps.
	bAttackHitsMultipleTargets = false;

	// Enemies never own the view. Leaving the rig enabled would give every
	// spawned creature a camera competing to become the view target.
	bEnableCameraRig = false;

	// A plain AAIController, with no Behavior Tree and no navmesh. It exists
	// only so the pawn is possessed: UCharacterMovementComponent consumes the
	// accumulated control input through its controller, so AddMovementInput on
	// an unpossessed pawn would silently do nothing.
	AIControllerClass = AAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
}

void APTKEnemyCharacter::BeginPlay()
{
	Super::BeginPlay();

	Target = FindTarget();
	AttackCooldownRemaining = InitialAttackDelay;
	EnemyState = EPTKEnemyState::Idle;
}

float APTKEnemyCharacter::GetDistanceToTarget() const
{
	return Target ? FVector::Dist(GetActorLocation(), Target->GetActorLocation()) : -1.0f;
}

bool APTKEnemyCharacter::IsValidAttackVictim(const AActor* Victim) const
{
	// Hostile AND the actual target. Without the second half a bite aimed at
	// one body would also injure anything else standing in the arc - including
	// the King, once he became reachable at all.
	return Super::IsValidAttackVictim(Victim) && Victim == Target;
}

// ---------------------------------------------------------------------------
// Lanes
// ---------------------------------------------------------------------------

void APTKEnemyCharacter::AssignLaneRoute(FName RouteId)
{
	LaneRouteId = RouteId;
	LaneStep = 0;

	// Skip straight past any leading nodes already behind us. An enemy spawns
	// in a scattered ring around its portal, so some of them start slightly
	// beyond the portal node and would otherwise walk backwards to touch it
	// before setting off.
	if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		const int32 Length = Field->GetRouteLength(RouteId);
		while (LaneStep + 1 < Length
			&& FVector::Dist(GetActorLocation(),
				Field->GetRouteStepLocation(RouteId, LaneStep)) <= LaneNodeReachRadius)
		{
			++LaneStep;
		}
	}
}

float APTKEnemyCharacter::GetLaneProgress() const
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	return (Field && !LaneRouteId.IsNone())
		? Field->GetRouteProgress(LaneRouteId, GetActorLocation()) : 0.0f;
}

float APTKEnemyCharacter::GetDistanceFromLane() const
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	return (Field && !LaneRouteId.IsNone())
		? Field->DistanceToRoute(LaneRouteId, GetActorLocation()) : 0.0f;
}

bool APTKEnemyCharacter::GetLaneGoal(FVector& OutGoal) const
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	if (!Field || LaneRouteId.IsNone())
	{
		return false;
	}
	const int32 Length = Field->GetRouteLength(LaneRouteId);
	if (Length == 0)
	{
		return false;
	}
	OutGoal = Field->GetRouteStepLocation(LaneRouteId, FMath::Min(LaneStep, Length - 1));
	return true;
}

void APTKEnemyCharacter::AdvanceLaneIfArrived()
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	if (!Field || LaneRouteId.IsNone())
	{
		return;
	}
	const int32 Length = Field->GetRouteLength(LaneRouteId);
	while (LaneStep + 1 < Length
		&& FVector::Dist(GetActorLocation(),
			Field->GetRouteStepLocation(LaneRouteId, LaneStep)) <= LaneNodeReachRadius)
	{
		++LaneStep;
	}
}

AActor* APTKEnemyCharacter::FindLaneTarget() const
{
	// LANE-AWARE TARGETING.
	//
	// Only things within LaneEngageRadius of where this enemy is STANDING are
	// candidates. It is walking its lane, so what comes into range is whatever
	// that lane runs past - which is the whole mechanism by which pressure ends
	// up spread around the map instead of every horde converging on whichever
	// guard happens to be globally nearest.
	//
	// The King is in the candidate set on the same terms as everyone else. He is
	// only ever reachable at the END of a lane, so an enemy at its portal is
	// thousands of units away and cannot see him; one that has walked its whole
	// lane can, which is exactly the "eventually reach King" case.
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	if (!Field)
	{
		return nullptr;
	}

	const FVector Origin = GetActorLocation();
	AActor* Best = nullptr;
	float BestSq = FMath::Square(LaneEngageRadius);

	auto Consider = [this, &Origin, &Best, &BestSq](AActor* Candidate)
	{
		if (!Candidate || Candidate == this || !PTKCombat::IsHostileTarget(this, Candidate))
		{
			return;
		}
		const float Sq = FVector::DistSquared(Origin, Candidate->GetActorLocation());
		if (Sq < BestSq)
		{
			BestSq = Sq;
			Best = Candidate;
		}
	};

	for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
	{
		Consider(Guard);
	}
	for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
	{
		Consider(Base);
	}
	Consider(Field->GetKing());

	return Best;
}

AActor* APTKEnemyCharacter::FindTarget() const
{
	// On a lane, the lane decides. Off one - the development spawner, or an
	// enemy placed by hand - fall through to the global search below.
	if (!LaneRouteId.IsNone())
	{
		return FindLaneTarget();
	}

	// NEAREST VALID OBJECTIVE, by road distance.
	//
	// Guards and guard bases compete on equal terms - a base 120 units away is
	// taken over a guard 300 away, and the reverse. Neither outranks the other
	// by type, which is what makes a base worth defending rather than scenery
	// the enemy walks past on its way to a guard.
	//
	// The King is NOT in this contest. He is the fallback for when the whole
	// line is gone, and including him would let an enemy that spawned near the
	// centre ignore every defender and walk straight onto the objective.
	//
	// Distance is measured through the lane graph, not straight-line, so a base
	// on the far side of a treeline does not look close just because the crow
	// flies that way.
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	const FVector Origin = GetActorLocation();

	AActor* Best = nullptr;
	float BestDistance = TNumericLimits<float>::Max();

	auto Consider = [this, Field, &Origin, &Best, &BestDistance](AActor* Candidate)
	{
		if (!Candidate || Candidate == this || !PTKCombat::IsHostileTarget(this, Candidate))
		{
			return;
		}
		const FVector At = Candidate->GetActorLocation();
		const float Distance = Field
			? Field->GetPathDistance(Origin, At)
			: FVector::Dist(Origin, At);
		if (Distance < BestDistance)
		{
			BestDistance = Distance;
			Best = Candidate;
		}
	};

	if (Field)
	{
		// Cached registries rather than an actor iterator: this runs per enemy
		// on a timer, and at a few hundred enemies a full level scan each time
		// is the difference between a frame and a stall.
		for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
		{
			Consider(Guard);
		}
		for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
		{
			Consider(Base);
		}
	}
	else
	{
		for (TActorIterator<APTKTopDownCharacter> It(GetWorld()); It; ++It)
		{
			Consider(*It);
		}
	}

	if (Best)
	{
		return Best;
	}

	// Nothing left standing: the King. Reached only once every guard is dead
	// and every base destroyed, which is exactly the fallback the spec asks for.
	if (Field)
	{
		if (APTKKingCharacter* King = Field->GetKing())
		{
			if (PTKCombat::IsHostileTarget(this, King))
			{
				return King;
			}
		}
		return nullptr;
	}

	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		AActor* const Candidate = *It;
		if (Candidate != this && PTKCombat::IsHostileTarget(this, Candidate))
		{
			Consider(Candidate);
		}
	}
	return Best;
}

FVector2D APTKEnemyCharacter::ToScreenSpace(const FVector& WorldOffset) const
{
	// Project a world offset onto the screen basis so the result is in the same
	// convention IA_Move produces. Asking the camera rig rather than assuming
	// +X is screen-right is what keeps enemies from moving mirrored.
	return FVector2D(FVector::DotProduct(WorldOffset, MovementRightVector),
	                 FVector::DotProduct(WorldOffset, MovementUpVector));
}

FVector2D APTKEnemyCharacter::ComputeBearingTo(const FVector& TargetLocation) const
{
	// Pure direction to the target, with no crowd avoidance mixed in. Facing is
	// chosen from THIS rather than from the steering vector: an enemy shouldering
	// past a neighbour should still look at what it is attacking, not at wherever
	// separation happens to be pushing it.
	FVector2D Bearing = ToScreenSpace(TargetLocation - GetActorLocation());
	const float Size = Bearing.Size();
	return (Size > KINDA_SMALL_NUMBER) ? (Bearing / Size) : FVector2D::ZeroVector;
}

FVector2D APTKEnemyCharacter::ComputeSeparation() const
{
	// Deliberately not flocking - no alignment, no cohesion, no neighbour lists.
	// Just a short push away from anyone standing too close, which is enough to
	// stop ten creatures converging on one point and jamming.
	//
	// The query is a sphere overlap rather than an actor iteration so the cost
	// stays with the physics broadphase instead of growing with level size.
	UWorld* const World = GetWorld();
	if (!World || SeparationRadius <= 0.0f)
	{
		return FVector2D::ZeroVector;
	}

	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKEnemySeparation), false, this);
	Params.AddIgnoredActor(this);

	World->OverlapMultiByObjectType(
		Overlaps, GetActorLocation(), FQuat::Identity,
		FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(SeparationRadius), Params);

	FVector2D Push = FVector2D::ZeroVector;
	for (const FOverlapResult& Result : Overlaps)
	{
		const APTKEnemyCharacter* const Other = Cast<APTKEnemyCharacter>(Result.GetActor());
		if (!Other || Other == this || Other->IsDead())
		{
			continue;
		}

		const FVector Away = GetActorLocation() - Other->GetActorLocation();
		const float Distance = Away.Size();
		if (Distance <= KINDA_SMALL_NUMBER)
		{
			// Exactly co-located - two spawns landed on the same point. Any
			// direction will do, but it must be deterministic per pair or the
			// pair will jitter against each other forever.
			Push += FVector2D(GetUniqueID() % 2 ? 1.0f : -1.0f, 0.0f);
			continue;
		}
		if (Distance >= SeparationRadius)
		{
			continue;
		}

		// Linear falloff: touching pushes hardest, at the radius it is zero.
		const float Strength = 1.0f - (Distance / SeparationRadius);
		Push += ToScreenSpace(Away / Distance) * Strength;
	}
	return Push;
}

FVector2D APTKEnemyCharacter::ComputeDesiredInput(const FVector& TargetLocation) const
{
	// Steers straight at whatever it is given, plus a nudge away from
	// neighbours. Choosing WHERE to go is the caller's job now: an enemy on a
	// lane is handed its next lane node, and only ever handed a target it is
	// already close enough to reach without leaving the road.
	//
	// The previous version re-solved a shortest path here on every frame from
	// wherever the enemy happened to be standing. That is what let a crowd drift
	// off the road and then re-route across the terrain - each frame it would
	// snap to whichever node was nearest to its drifted position and cut the
	// corner toward it.
	FVector Steer = TargetLocation;

	// Unassigned enemies keep the old graph-walking behaviour, so the
	// development spawner and hand-placed enemies still path sensibly.
	if (LaneRouteId.IsNone())
	{
		if (const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
		{
			FVector Step;
			if (FVector::Dist(GetActorLocation(), TargetLocation) > LaneEngageRadius
				&& Field->GetNextLaneStep(GetActorLocation(), TargetLocation, Step))
			{
				Steer = Step;
			}
		}
	}

	FVector2D Input = ComputeBearingTo(Steer) + ComputeSeparation() * SeparationWeight;

	const float Size = Input.Size();
	return (Size > KINDA_SMALL_NUMBER) ? (Input / Size) : FVector2D::ZeroVector;
}

void APTKEnemyCharacter::HandleDeath(AActor* Killer)
{
	// Clear the AI first so nothing below can re-enter Chase or Attack while
	// the base class is tearing the character down.
	EnemyState = EPTKEnemyState::Dead;
	Target = nullptr;
	AttackCooldownRemaining = 0.0f;

	Super::HandleDeath(Killer);
}

void APTKEnemyCharacter::FireProjectile()
{
	if (IsDead() || !GetWorld() || !ProjectileClass || !IsValidAttackVictim(Target)) return;
	// Keep four-direction animation, but aim the flight at the actual target.
	const FVector Aim = (Target->GetActorLocation() - GetActorLocation()).GetSafeNormal();
	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.Instigator = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	APTKProjectile* Shot = GetWorld()->SpawnActor<APTKProjectile>(ProjectileClass,
		GetActorLocation(), FRotator::ZeroRotator, Params);
	if (Shot)
	{
		Shot->SetIntendedTarget(Target);
		Shot->Launch(Aim, FacingDirection, this, Team, GetEffectiveAttackDamage(),
			ProjectileSpeed, GetAttackReach(), MuzzleHeightOffset, MovementUpVector);
	}
}

void APTKEnemyCharacter::Tick(float DeltaSeconds)
{
	// The base Tick runs the movement, facing and animation state machine, and
	// returns immediately once dead. The AI below only decides what to feed it.
	Super::Tick(DeltaSeconds);

	if (EnemyState == EPTKEnemyState::Dead || IsDead())
	{
		return;
	}

	if (AttackCooldownRemaining > 0.0f)
	{
		AttackCooldownRemaining = FMath::Max(0.0f, AttackCooldownRemaining - DeltaSeconds);
	}

	// Re-acquire the moment the current target stops being a target - not on
	// the next scheduled refresh. Otherwise an enemy keeps swinging at a fresh
	// corpse for up to TargetRefreshInterval before noticing.
	TargetRefreshTimer -= DeltaSeconds;
	if (!PTKCombat::IsEngageable(Target) || TargetRefreshTimer <= 0.0f)
	{
		TargetRefreshTimer = TargetRefreshInterval;
		AActor* const Reacquired = FindTarget();
		if (Reacquired != Target)
		{
			UE_LOG(LogPTK, Log, TEXT("%s target: %s -> %s"),
				*GetName(), *GetNameSafe(Target), *GetNameSafe(Reacquired));
			Target = Reacquired;
		}
	}

	// Once a second, on one line: everything needed to answer "why is it not
	// attacking" without attaching a debugger or reading the on-screen panel.
	DiagnosticTimer -= DeltaSeconds;
	if (DiagnosticTimer <= 0.0f)
	{
		DiagnosticTimer = 1.0f;
		UE_LOG(LogPTK, Verbose,
			TEXT("%s state=%s target=%s dist=%.0f controller=%s speed=%.0f cd=%.2f"),
			*GetName(), *UPTKTypesLibrary::EnemyStateToString(EnemyState),
			*GetNameSafe(Target), GetDistanceToTarget(),
			*GetNameSafe(GetController()), GetVelocity().Size(),
			AttackCooldownRemaining);
	}

	if (bDrawPerceptionRanges)
	{
		const FVector Centre = GetActorLocation();
		const FVector Axis = MovementDepthVector.GetSafeNormal();
		DrawDebugCircle(GetWorld(), Centre, DetectionRange, 48, FColor(60, 60, 200), false, -1.0f, 0,
			1.0f, MovementRightVector, MovementUpVector, false);
		DrawDebugCircle(GetWorld(), Centre, GetAttackReach(), 32, FColor::Red, false, -1.0f, 0,
			1.0f, MovementRightVector, MovementUpVector, false);
		(void)Axis;
	}

	// An attack owns the character until its animation finishes. Not steering
	// during it is what makes the enemy plant itself and swing instead of
	// sliding forward mid-strike.
	if (IsAttacking())
	{
		SetMoveInput(FVector2D::ZeroVector);
		return;
	}

	// Nothing to fight: keep marching the lane. An enemy is an attacker with
	// somewhere to be, so "no target" means "advance", not "stand still" - and
	// resuming here is also how it returns to the road after a fight beside it
	// finishes, without needing any explicit re-join step.
	if (!Target)
	{
		AdvanceLaneIfArrived();

		FVector Goal;
		if (GetLaneGoal(Goal))
		{
			EnemyState = EPTKEnemyState::Chase;
			SetMoveInput(ComputeDesiredInput(Goal));
		}
		else
		{
			EnemyState = EPTKEnemyState::Idle;
			SetMoveInput(FVector2D::ZeroVector);
		}
		return;
	}

	const float Distance = FVector::Dist(GetActorLocation(), Target->GetActorLocation());

	// NOTE: there is deliberately no "further than DetectionRange, so stand
	// still" case any more. That rule belonged to a small test arena where
	// everything started within sight of everything else. On the real map an
	// enemy spawns in a corner thousands of units from any objective, and
	// waiting to notice one would leave the whole horde standing at the portal
	// forever. An enemy is an attacker: it advances on its objective from
	// wherever it lands. DetectionRange now only tunes the diagnostic ring.

	// The tolerance band stops a target hovering exactly on AttackRange from
	// flipping the state - and therefore the animation - every single frame.
	// The stop distance IS the attack reach, so the enemy can never halt
	// somewhere its own swing cannot land.
	const float Reach = GetAttackReach();
	const float LeaveRange = Reach + AttackRangeTolerance;
	const bool bInRange = (EnemyState == EPTKEnemyState::Attack)
		? (Distance <= LeaveRange)
		: (Distance <= Reach);

	if (!bInRange)
	{
		EnemyState = EPTKEnemyState::Chase;
		SetMoveInput(ComputeDesiredInput(Target->GetActorLocation()));
		return;
	}

	// In range: stop, face the target, swing when recovered.
	EnemyState = EPTKEnemyState::Attack;
	SetMoveInput(FVector2D::ZeroVector);

	// Facing still has to be updated even though there is no movement input,
	// because the base class only refreshes it while moving. Feeding the
	// direction-from-input rule the same vector chase would have used keeps the
	// enemy's attack facing consistent with its walk facing.
	const FVector2D Bearing = ComputeBearingTo(Target->GetActorLocation());
	SetFacingDirection(UPTKTypesLibrary::DirectionFromInput(
		Bearing, GetFacingDirection(), MoveDeadZone, FacingHysteresis));

	if (AttackCooldownRemaining <= 0.0f)
	{
		if (StartAttack())
		{
			// Cooldown is measured from the end of the swing, so it reads as
			// recovery rather than as an overlapping timer.
			AttackCooldownRemaining = AttackCooldown + AttackTimeRemaining;
		}
	}
}
